"""Abruf der onvista-Daten und Umwandlung in einfache Datensätze.

Es wird nichts umgangen: ehrlicher User-Agent, bei 403/429 sofort Abbruch.
"""
import json
import math
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# Quelle: SPEC.md, Abschnitt "Datenquelle onvista" (Abruf getestet am 09.11.2026)
BASIS_URL = "https://api.onvista.de/api/v1"
USER_AGENT = "discount-tracker/1.0 (privat)"
TIMEOUT_S = 20
WIEDERHOLUNGEN = 2
WARTEZEIT_S = 2.0
MAX_BYTES = 8_000_000
BERLIN = ZoneInfo("Europe/Berlin")
DAX_ISIN = "DE0008469008"
# eod_history liefert ab startDate vorwärts; Länge je range (geprüft am 09.11.2026: M1/M3/M6/Y1).
RANGES = (("M1", 28), ("M3", 85), ("M6", 175), ("Y1", 360))
PFADE = {"STOCK": "stocks", "INDEX": "indices"}


class AbrufFehler(Exception):
    """Abruf fehlgeschlagen (Netz, Serverfehler)."""


class GesperrtFehler(AbrufFehler):
    """403/429: Der Dienst sperrt den Abruf. Es wird nicht umgangen."""


class DatenFehler(AbrufFehler):
    """Antwort kam an, passt aber nicht zum erwarteten Aufbau."""


def hole_bytes(url, *, oeffnen=None, schlafen=time.sleep, max_bytes=MAX_BYTES):
    """GET mit Timeout und bis zu zwei Wiederholungen bei 5xx/Netzfehler."""
    if not url.startswith("https://"):
        raise AbrufFehler("Nur https-Adressen sind erlaubt.")
    oeffnen = oeffnen or urllib.request.urlopen
    letzter = None
    for versuch in range(WIEDERHOLUNGEN + 1):
        if versuch:
            schlafen(WARTEZEIT_S * versuch)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with oeffnen(req, timeout=TIMEOUT_S) as antwort:
                inhalt = antwort.read(max_bytes + 1)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise GesperrtFehler(f"Der Dienst hat den Abruf abgelehnt (HTTP {e.code}). Kein Umgehen, Lauf wird beendet.") from None
            if e.code < 500:
                raise AbrufFehler(f"HTTP {e.code} beim Abruf.") from None
            letzter = f"HTTP {e.code}"
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            letzter = f"Netzfehler ({type(e).__name__})"
            continue
        if len(inhalt) > max_bytes:
            raise AbrufFehler("Antwort ist größer als erlaubt.")
        return inhalt
    raise AbrufFehler(f"Abruf fehlgeschlagen nach {WIEDERHOLUNGEN + 1} Versuchen: {letzter}.")


def hole_json(url, **kw):
    try:
        return json.loads(hole_bytes(url, **kw))
    except ValueError:
        raise DatenFehler("Antwort ist kein gültiges JSON.") from None


def _zahl(wert):
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        return None
    return float(wert)


def _kurs(wert):
    """Wie _zahl, aber ein Kurs muss endlich und größer als 0 sein."""
    z = _zahl(wert)
    return z if z is not None and math.isfinite(z) and z > 0 else None


def _zeit(text):
    try:
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _berlin_datum(text):
    z = _zeit(text)
    if z is None:
        return None
    # Ohne Zone würde astimezone die Systemzone annehmen: PC und Runner kämen zu verschiedenen Tagen.
    return (z if z.tzinfo else z.replace(tzinfo=ZoneInfo("UTC"))).astimezone(BERLIN).date()


def parse_zertifikat(d):
    """Stammdaten, Kurse und Kennzahlen aus dem Zertifikats-Snapshot."""
    try:
        sub = d["derivativesDetails"]["derivativesSubCategory"]["entitySubType"]
        if sub != "DISCOUNT_CERTIFICATE":
            raise DatenFehler(f"Kein Discount-Zertifikat (Typ {sub}).")
        liste = d["derivativesUnderlyingList"]["list"]
        if not liste:
            raise DatenFehler("Zertifikat ohne Basiswert.")
        u = liste[0]
        basis = u["instrument"]
        quote, fig, inst = d["quote"], d.get("derivativesFigure") or {}, d["instrument"]
    except (KeyError, TypeError):
        raise DatenFehler("Zertifikats-Snapshot hat einen unerwarteten Aufbau.") from None
    caps = [b.get("barrier") for b in (u.get("derivativesBarrierList") or {}).get("list", []) if b.get("typeBarrier") == "CAP"]
    maturity = _zeit(d["derivativesDetails"].get("datetimeMaturity"))
    return {
        "isin": inst.get("isin"), "wkn": inst.get("wkn"), "name": inst.get("name"),
        "emittent": (d.get("derivativesIssuer") or {}).get("name"),
        "faellig": maturity.date().isoformat() if maturity else None,
        "cap": _zahl(caps[0]) if caps else None,
        "bezug": _zahl(u.get("coverRatio")) or 1.0,
        "basis_name": basis.get("name"), "basis_isin": basis.get("isin"),
        "basis_art": basis.get("entityType"), "basis_entity": str(basis.get("entityValue")),
        "basis_notation": (u.get("market") or {}).get("idNotation"),
        "entity": str(inst.get("entityValue")), "notation": (quote.get("market") or {}).get("idNotation"),
        "z_geld": _kurs(quote.get("bid")), "z_brief": _kurs(quote.get("ask")),
        "datum_berlin": _berlin_datum(quote.get("datetimeLast")),
        "delta": _zahl(fig.get("deltaBid")), "theta_tag": _zahl(fig.get("thetaDay")),
        "iv": _zahl(fig.get("impliedVolatilityAsk")),
        "max_ertrag_eur": _zahl(fig.get("maximumEarningBid")), "max_ertrag_pct": _zahl(fig.get("maximumEarningBidPct")),
        "discount_pct": _zahl(fig.get("discountPct")),
    }


def parse_xetra(d, art):
    """Xetra-Eintrag aus der Notierungsliste (Aktie: codeMarket _GER, Index: Name Xetra)."""
    try:
        liste = d["quoteList"]["list"]
        inst = d["instrument"]
    except (KeyError, TypeError):
        raise DatenFehler("Snapshot hat einen unerwarteten Aufbau.") from None
    for q in liste:
        m = q.get("market") or {}
        passt = m.get("codeMarket") == "_GER" if art == "STOCK" else m.get("name") == "Xetra"
        if passt:
            return {
                "last": _kurs(q.get("last")), "notation": m.get("idNotation"),
                "entity": str(q.get("entityValue") or inst.get("entityValue")),
                "datum_berlin": _berlin_datum(q.get("datetimeLast")),
                "prepost": bool(q.get("prePostTrading")),
            }
    raise DatenFehler("Kein Xetra-Eintrag im Snapshot gefunden.")


def parse_historie(d):
    """Parallele Listen datetimeLast/last → {ISO-Datum: Schlusskurs}, aufsteigend."""
    erg = {}
    for ts, kurs in zip(d.get("datetimeLast") or [], d.get("last") or []):
        k = _kurs(kurs)
        if k is None or not isinstance(ts, (int, float)):
            continue
        erg[datetime.fromtimestamp(ts, ZoneInfo("UTC")).date().isoformat()] = k
    return dict(sorted(erg.items()))


def range_fuer(start, ende):
    tage = (ende - start).days
    for name, maximal in RANGES:
        if tage <= maximal:
            return name
    return RANGES[-1][0]


def historie_url(art, entity, notation, start, ende):
    return (f"{BASIS_URL}/instruments/{art}/{entity}/eod_history"
            f"?idNotation={notation}&range={range_fuer(start, ende)}&startDate={start.isoformat()}")


def snapshot_url(art, isin):
    pfad = "derivatives" if art == "DERIVATIVE" else PFADE[art]
    return f"{BASIS_URL}/{pfad}/ISIN:{isin}/snapshot"


def lade_historie(art, entity, notation, start, ende, **kw):
    return parse_historie(hole_json(historie_url(art, entity, notation, start, ende), **kw))


def lade_alles(isin, start, heute, **kw):
    """Snapshots (Zertifikat, Basiswert, DAX) und Historien ab start. Rückgabe: ein Dict."""
    z = parse_zertifikat(hole_json(snapshot_url("DERIVATIVE", isin), **kw))
    art = z["basis_art"] if z["basis_art"] in PFADE else "STOCK"
    basis = parse_xetra(hole_json(snapshot_url(art, z["basis_isin"]), **kw), art)
    dax = parse_xetra(hole_json(snapshot_url("INDEX", DAX_ISIN), **kw), "INDEX")
    hist = {
        "z": lade_historie("DERIVATIVE", z["entity"], z["notation"], start, heute, **kw),
        "basis": lade_historie(art, z["basis_entity"], z["basis_notation"], start, heute, **kw),
        "dax": lade_historie("INDEX", dax["entity"], dax["notation"], start, heute, **kw),
    }
    return {"zertifikat": z, "basis": basis, "dax": dax, "historie": hist, "basis_art": art}


def historie_start(laufstart, heute):
    """Ältester Tag der Historie: 90 Tage vor Laufstart (nie nach heute)."""
    return min(laufstart, heute) - timedelta(days=90)


__all__ = ["AbrufFehler", "GesperrtFehler", "DatenFehler", "hole_bytes", "hole_json", "parse_zertifikat",
           "parse_xetra", "parse_historie", "range_fuer", "historie_url", "lade_alles", "historie_start"]
