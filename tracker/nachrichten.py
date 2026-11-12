"""Schlagzeilen aus Google-News-RSS: Abruf, Einordnung per Stichwort, Zuordnung zum Handelstag.

Externe Schlagzeilen sind nicht vertrauenswürdig: nur https-Links, XML ohne DOCTYPE/Entities
(Standardbibliothek), begrenzte Größe, kein Artikeltext. Fehler brechen den Lauf nie ab.
"""
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from tracker.onvista import AbrufFehler, GesperrtFehler

# Quelle: SPEC.md, Abschnitt "Nachrichten"
BERLIN = ZoneInfo("Europe/Berlin")
MAX_RSS_BYTES = 1_000_000
RSS_URL = "https://news.google.com/rss/search?q={q}+after:{von}+before:{bis}&hl=de&gl=DE&ceid=DE:de"
XETRA_SCHLUSS = (17, 35)
MAX_TAGE_ZURUECK = 14
TOP_N = 3
MAX_GESPEICHERT = 30    # je Handelstag; Google liefert bis zu 100 Treffer je Abfrage, das wäre unnötig viel Speicher
PAUSE_S = 1.5
MAX_FEHLTAGE_IN_FOLGE = 2   # Annahme: Wer zwei Tage nacheinander nicht antwortet, ist gerade gestört
MAX_SEKUNDEN = 120          # Zeitbudget je Lauf, damit der Commit der Kurse sicher noch drankommt
DAX_GROSS_PCT = 1.0     # Annahme: ab 1 % DAX-Änderung gilt die Bewegung als Marktbewegung
# Reihenfolge = Vorrang. Schlüsselwörter klein geschrieben, als Teilstrings (Annahme: reicht für Überschriften).
KATEGORIEN = (
    ("Analyst/Kursziel", ("analyst", "kursziel", "kaufempfehlung", "abgestuft", "hochgestuft", "outperform", "overweight", "underweight", "einstufung")),
    ("Quartalszahlen", ("quartal", "halbjahr", "jahreszahlen", "geschäftszahlen", "umsatz", "ergebnis", "bilanz")),
    ("Prognose", ("prognose", "ausblick", "gewinnwarnung", "erwartungen", "guidance", "cloud-umsatz")),
    ("Übernahme/Beteiligung", ("übernahme", "übernimmt", "kauft", "kaufen ", "beteiligung", "fusion", "verkauft", "zukauf", "investiert in")),
    ("Dividende/Rückkauf", ("dividende", "rückkauf", "ausschüttung")),
    ("Recht/Regulierung", ("klage", "kartell", "strafe", "verfahren", "regulier", "gericht", "ermittlung", "prozess")),
    ("Personalie", ("finanzchef", "vorstand", "ceo", "chef ", "rücktritt", "aufsichtsrat", "nachfolger", "personalie")),
    ("Makro", ("ezb", "zins", "inflation", "zoll", "konjunktur", "fed ", "notenbank", "arbeitsmarkt", "ifo", "bip", "rezession", "trump")),
)
POSITIV = ("hebt", "erhöht", "übertrifft", "kurssprung", "rekord", "steigt", "springt", "legt zu", "stark")
NEGATIV = ("senkt", "verfehlt", "gewinnwarnung", "bricht ein", "absturz", "klage", "fällt", "verliert", "schwach", "einbruch")
UNTERNEHMEN_AUSGENOMMEN = ("Makro", "Sonstiges")


class NachrichtenFehler(Exception):
    """RSS-Antwort unbrauchbar oder verdächtig."""


def begriffe(basis_name, suchbegriff):
    return [suchbegriff or f"{basis_name} Aktie", "DAX"]


def url_fuer(begriff, tag):
    return RSS_URL.format(q=urllib.parse.quote(begriff), von=(tag - timedelta(days=1)).isoformat(),
                          bis=(tag + timedelta(days=1)).isoformat())


def _vorheriger_werktag(tag):
    d = tag - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def fenster(tag, vortag=None):
    """Xetra-Schluss des Vortags bis Xetra-Schluss am Tag (Berlin). Wochenenden gehen in den Montag."""
    vortag = vortag or _vorheriger_werktag(tag)
    h, m = XETRA_SCHLUSS
    return (datetime(vortag.year, vortag.month, vortag.day, h, m, tzinfo=BERLIN),
            datetime(tag.year, tag.month, tag.day, h, m, tzinfo=BERLIN))


def braucht_nachrichten(datum, vorhanden, heute):
    d = date.fromisoformat(datum)
    return datum not in vorhanden and timedelta(0) <= heute - d <= timedelta(days=MAX_TAGE_ZURUECK)


def _text(el, name):
    k = el.find(name)
    return (k.text or "").strip() if k is not None and k.text else ""


def _zeit(text):
    try:
        return parsedate_to_datetime(text).astimezone(BERLIN)
    except (TypeError, ValueError):
        return None


def parse_rss(daten):
    """RSS-Bytes → Liste {titel, quelle, zeit (ISO Berlin), url (nur https)}."""
    if len(daten) > MAX_RSS_BYTES:
        raise NachrichtenFehler("RSS-Antwort ist zu groß.")
    oben = daten.upper()
    if b"<!DOCTYPE" in oben or b"<!ENTITY" in oben:
        raise NachrichtenFehler("RSS enthält DOCTYPE oder Entities und wird nicht verarbeitet.")
    try:
        wurzel = ET.fromstring(daten)
    except ET.ParseError:
        raise NachrichtenFehler("RSS ist kein gültiges XML.") from None
    erg = []
    for item in wurzel.iter("item"):
        titel, quelle = _text(item, "title"), _text(item, "source")
        if not titel:
            continue
        if quelle and titel.endswith(" - " + quelle):
            titel = titel[: -len(quelle) - 3].rstrip()
        link = _text(item, "link")
        z = _zeit(_text(item, "pubDate"))
        erg.append({"titel": titel, "quelle": quelle or None,
                    "zeit": z.isoformat(timespec="seconds") if z else None,
                    "url": link if link.startswith("https://") else None})
    return erg


def ordne_ein(titel):
    t = titel.lower() + " "
    kat = next((name for name, woerter in KATEGORIEN if any(w in t for w in woerter)), "Sonstiges")
    pos, neg = any(w in t for w in POSITIV), any(w in t for w in NEGATIV)
    richtung = "positiv" if pos and not neg else "negativ" if neg and not pos else "neutral"
    return kat, richtung


def passt(kategorie, richtung, aktie_spez_pct, dax_pct):
    """True, wenn die Richtung zur Bewegung passt; False gegenläufig; None bei neutral/ohne Bewegung."""
    if richtung == "neutral":
        return None
    bewegung = dax_pct if kategorie == "Makro" else aktie_spez_pct
    if bewegung is None or bewegung == 0:
        return None
    return (richtung == "positiv") == (bewegung > 0)


def _name_im_titel(name, titel):
    return bool(name) and re.search(r"\b" + re.escape(name) + r"\b", titel, re.IGNORECASE) is not None


def bewerte(roh, tag, basis_name):
    """Roh-Schlagzeilen einordnen und die TOP_N relevantesten zurückgeben."""
    bewertet = []
    for r in roh:
        kat, richtung = ordne_ein(r["titel"])
        p = passt(kat, richtung, tag.get("aktie_spez_pct"), tag.get("dax_pct"))
        punkte = _name_im_titel(basis_name, r["titel"]) + (kat != "Sonstiges") + (p is True)
        bewertet.append((punkte, r.get("zeit") or "", dict(r, kategorie=kat, richtung=richtung, passt=p)))
    bewertet.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [b[2] for b in bewertet[:TOP_N]]


def verdikt(tag, news):
    """Regelbasierte Einordnung. Beschreibt zeitlichen Zusammenhang, nie einen Beweis."""
    if tag.get("auffaellig") is None:
        return None
    firma = [x for x in news if x["kategorie"] not in UNTERNEHMEN_AUSGENOMMEN]
    makro = [x for x in news if x["kategorie"] == "Makro" and x["passt"] is not False]
    if tag["auffaellig"] and any(x["passt"] is True for x in firma):
        return "Wahrscheinlicher Zusammenhang"
    if (abs(tag["effekt_markt"] or 0) > abs(tag["effekt_aktie"] or 0) or makro
            or abs(tag.get("dax_pct") or 0) >= DAX_GROSS_PCT):
        return "Marktbewegung"
    if not tag["auffaellig"]:
        return "Im normalen Rauschen"
    return "Möglicher Zusammenhang" if firma else "Keine Erklärung gefunden"


def _vorauswahl(liste, basis_name):
    """Die MAX_GESPEICHERT wahrscheinlich wichtigsten Schlagzeilen (Name im Titel, echte Kategorie)."""
    def punkte(i):
        return _name_im_titel(basis_name, i["titel"]) + (ordne_ein(i["titel"])[0] != "Sonstiges")
    return sorted(liste, key=punkte, reverse=True)[:MAX_GESPEICHERT]


def _im_fenster(item, von, bis):
    if not item["zeit"]:
        return False
    return von <= datetime.fromisoformat(item["zeit"]) <= bis


def _hole_tag(datum, begriff_liste, fetch, pause, basis_name):
    """Alle Treffer des Tages im Fenster. Rückgabe (Liste, ok); ok=False, wenn keine Abfrage gelang."""
    tag = date.fromisoformat(datum)
    von, bis = fenster(tag)
    funde, ok = [], False
    for b in begriff_liste:
        try:
            items = parse_rss(fetch(url_fuer(b, tag)))
            ok = True
        except GesperrtFehler:
            raise
        except (AbrufFehler, NachrichtenFehler):
            continue
        finally:
            pause()
        funde += [i for i in items if _im_fenster(i, von, bis)]
    gesehen, eindeutig = set(), []
    for f in funde:
        if f["titel"] not in gesehen:
            gesehen.add(f["titel"])
            eindeutig.append(f)
    return _vorauswahl(eindeutig, basis_name), ok


def sammle(datums, vorhanden, heute, fetch, basis_name, suchbegriff, pause=lambda: time.sleep(PAUSE_S),
           uhr=time.monotonic):
    """Fehlende Tage abfragen. Rückgabe {datum: [roh]} nur für Tage, bei denen mindestens eine Abfrage klappte.

    Stoppt bei Sperre, nach mehreren Fehltagen in Folge und nach dem Zeitbudget: Kurse gehen vor Schlagzeilen.
    """
    erg, bl, fehltage, start = {}, begriffe(basis_name, suchbegriff), 0, uhr()
    for d in datums:
        if not braucht_nachrichten(d, vorhanden, heute):
            continue
        if fehltage >= MAX_FEHLTAGE_IN_FOLGE or uhr() - start > MAX_SEKUNDEN:
            break
        try:
            liste, ok = _hole_tag(d, bl, fetch, pause, basis_name)
        except GesperrtFehler:
            break
        fehltage = 0 if ok else fehltage + 1
        if ok:
            erg[d] = liste
    return erg
