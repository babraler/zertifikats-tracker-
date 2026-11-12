"""Einstieg: python lauf.py [--neu-bauen]

Abfolge: Snapshot Zertifikat → Historien (Lücken füllen) → heutige Zeile → Nachrichten → Auswertung → Ausgabe.
--neu-bauen: ohne Netz, nur Auswertung und Ausgabe aus den gespeicherten Daten.
Alle Pfade liegen relativ zur Projektwurzel (läuft so auch auf dem GitHub-Runner).
"""
import argparse
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tracker import daten as daten_modul
from tracker import excel, nachrichten, onvista, seite, speicher

WURZEL = Path(__file__).resolve().parent
BERLIN = ZoneInfo("Europe/Berlin")
ISIN_MUSTER = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
NEWS_PAUSE_S = 1.5
EXIT_OK, EXIT_ABRUF, EXIT_CONFIG = 0, 1, 2


class ConfigFehler(Exception):
    pass


def lade_config(pfad):
    try:
        c = json.loads(Path(pfad).read_text(encoding="utf-8"))
        if not (isinstance(c["isin"], str) and ISIN_MUSTER.match(c["isin"])):
            raise ConfigFehler("config.json: isin ist keine gültige ISIN.")
        date.fromisoformat(c["start"])
        if not (isinstance(c["wochen"], int) and 1 <= c["wochen"] <= 52):
            raise ConfigFehler("config.json: wochen muss eine Zahl von 1 bis 52 sein.")
        begriff = c.get("basis_suchbegriff")
        if begriff is not None and not (isinstance(begriff, str) and 0 < len(begriff) <= 100):
            raise ConfigFehler("config.json: basis_suchbegriff muss null oder ein kurzer Text sein.")
        return {"isin": c["isin"], "demo": bool(c.get("demo", False)), "start": c["start"],
                "wochen": c["wochen"], "basis_suchbegriff": begriff}
    except ConfigFehler:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise ConfigFehler("config.json fehlt oder ist unlesbar (nötig: isin, start, wochen).") from None


def _meta_neu(z, heute, handelstag, jetzt):
    keys = ("isin", "wkn", "name", "emittent", "cap", "bezug", "faellig", "basis_name", "basis_isin")
    return {
        "produkt": {k: z[k] for k in keys},
        "kennzahlen": {k: z[k] for k in ("max_ertrag_eur", "max_ertrag_pct", "discount_pct")},
        "abruf": {"datum": heute.isoformat(), "handelstag": handelstag.isoformat() if handelstag else None,
                  "zeit": jetzt.isoformat(timespec="seconds")},
        "quelle": "onvista.de",
    }


def _snapshot_werte(r, handelstag):
    z, b, d = r["zertifikat"], r["basis"], r["dax"]
    werte = {}
    if z["datum_berlin"] == handelstag:
        werte.update({k: z[k] for k in ("z_geld", "z_brief", "delta", "theta_tag", "iv")})
    # Nach Xetra-Schluss ist "last" ein Nachbörsenwert (prePostTrading): dann zählt der Schlusskurs der Historie.
    if not b["prepost"] and b["datum_berlin"] == handelstag:
        werte["basis"] = b["last"]
    if not d["prepost"] and d["datum_berlin"] == handelstag:
        werte["dax"] = d["last"]
    return werte


def abruf(config, rows, jetzt, **kw):
    """Netzabruf. Rückgabe (rows, meta, hinweis)."""
    heute = jetzt.date()
    start = onvista.historie_start(daten_modul.lauf_start(config), heute)
    r = onvista.lade_alles(config["isin"], start, heute, **kw)
    rows = speicher.fuelle_historie(rows, r["historie"])
    handelstag, hinweis = _handelstag(r, heute), ""
    if handelstag == heute:
        rows = speicher.fuelle_snapshot(rows, heute.isoformat(), _snapshot_werte(r, handelstag))
    elif handelstag is None:
        hinweis = "Handelstag nicht erkennbar, der nächste Lauf versucht es erneut."
    else:
        hinweis = f"Heute ({heute.isoformat()}) kein Handelstag, letzter Handelstag {handelstag}."
    return rows, _meta_neu(r["zertifikat"], heute, handelstag, jetzt), hinweis


def _handelstag(r, heute):
    """Heute, wenn Aktie oder DAX heute notieren. Feiertag nur, wenn beide denselben früheren Tag zeigen; sonst None."""
    b, d = r["basis"]["datum_berlin"], r["dax"]["datum_berlin"]
    if heute in (b, d):
        return heute
    return b if b is not None and b == d else None


def schon_erledigt(rows, meta, heute):
    if speicher.ist_vollstaendig(rows.get(heute.isoformat())):
        return True
    a = meta.get("abruf", {})
    return a.get("datum") == heute.isoformat() and a.get("handelstag") not in (None, heute.isoformat())


def hole_nachrichten(config, meta, rows, pfad, heute, fetch, schlafen):
    """Fehlende Schlagzeilen speichern. Fehler hier brechen den Lauf nie ab."""
    try:
        name = meta.get("produkt", {}).get("basis_name") or "Basiswert"
        vorhanden = speicher.lies_nachrichten(pfad)
        neu = nachrichten.sammle(sorted(rows), vorhanden, heute, fetch, name, config["basis_suchbegriff"],
                                 pause=lambda: schlafen(NEWS_PAUSE_S))
        for d, liste in neu.items():
            speicher.haenge_nachrichten_an(pfad, d, liste)
    except Exception as e:  # bewusst breit: Nachrichten sind Beiwerk
        print(f"Hinweis: Nachrichten übersprungen ({type(e).__name__}).")


def erzeuge_ausgabe(config, meta, rows, pfad_news, jetzt, ok, meldung, wurzel):
    aus = wurzel / "ausgabe"
    d = daten_modul.baue_daten(config, meta, rows, speicher.lies_nachrichten(pfad_news), jetzt, ok, meldung)
    speicher.schreibe_json(aus / "daten.json", d)
    speicher.schreibe_json(aus / "status.json", d["status"])
    try:
        excel.schreibe(d, aus / "kurse.xlsx")
    except Exception as e:  # bewusst breit: Excel ist Beiwerk, Dashboard und Status sollen trotzdem entstehen
        print(f"Hinweis: kurse.xlsx konnte nicht geschrieben werden ({type(e).__name__}); ist die Datei geöffnet?")
    seite_ok, seite_meldung = seite.rendere(d, wurzel / "tracker" / "vorlage.html", aus / "index.html")
    if not seite_ok:
        print("Hinweis:", seite_meldung)


def main(argv=None, *, jetzt=None, oeffnen=None, schlafen=time.sleep, wurzel=WURZEL):
    p = argparse.ArgumentParser(description="Täglicher Kursspeicher für ein Discount-Zertifikat")
    p.add_argument("--neu-bauen", action="store_true", help="ohne Netz nur Auswertung und Ausgabe neu bauen")
    args = p.parse_args(argv)
    try:
        config = lade_config(wurzel / "config.json")
    except ConfigFehler as e:
        print(f"Fehler: {e}")
        return EXIT_CONFIG
    jetzt = jetzt or datetime.now(BERLIN)
    heute = jetzt.date()
    ordner = wurzel / "daten" / config["isin"]
    rows, meta = speicher.lies_kurse(ordner / "kurse.csv"), speicher.lies_meta(ordner / "meta.json")
    pfad_news = ordner / "nachrichten.jsonl"
    ausgabe_da = (wurzel / "ausgabe" / "daten.json").exists()
    ok, meldung = True, ""
    kw = {"oeffnen": oeffnen, "schlafen": schlafen}

    if args.neu_bauen:
        print("Neu bauen ohne Netz.")
    elif heute > daten_modul.lauf_ende(config):
        print(f"Laufende erreicht ({daten_modul.lauf_ende(config)}). Keine Abrufe mehr.")
        if ausgabe_da:
            return EXIT_OK
    elif schon_erledigt(rows, meta, heute) and ausgabe_da:
        print("Heute schon abgerufen. Kein neuer Abruf.")
        return EXIT_OK
    else:
        try:
            rows, meta, meldung = abruf(config, rows, jetzt, **kw)
            speicher.schreibe_kurse(ordner / "kurse.csv", rows)
            speicher.schreibe_meta(ordner / "meta.json", meta)
            fetch = lambda url: onvista.hole_bytes(url, max_bytes=nachrichten.MAX_RSS_BYTES, **kw)  # noqa: E731
            hole_nachrichten(config, meta, rows, pfad_news, heute, fetch, schlafen)
        except onvista.AbrufFehler as e:
            ok, meldung = False, str(e)
            print(f"Fehler beim Abruf: {meldung}")
        except Exception as e:  # bewusst breit: Das Dashboard darf nie "alles gut" zeigen, wenn der Lauf kaputt ist
            ok, meldung = False, f"Unerwarteter Fehler beim Abruf ({type(e).__name__})."
            print(meldung)
    try:
        erzeuge_ausgabe(config, meta, rows, pfad_news, jetzt, ok, meldung, wurzel)
    except Exception as e:  # bewusst breit: siehe oben
        ok, meldung = False, f"Unerwarteter Fehler in der Auswertung ({type(e).__name__})."
        print(meldung)
        speicher.schreibe_json(wurzel / "ausgabe" / "status.json",
                               {"ok": False, "meldung": meldung, "letzter_lauf": jetzt.isoformat(timespec="seconds")})
    print(f"Fertig: {len(rows)} Handelstage gespeichert, letzter Tag {max(rows) if rows else 'keiner'}.")
    return EXIT_OK if ok else EXIT_ABRUF


if __name__ == "__main__":
    for strom in (sys.stdout, sys.stderr):
        strom.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
