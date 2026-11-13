"""Einstieg: python lauf.py [--neu-bauen] [--isin ISIN]

Je Zertifikat aus config.json: Snapshot → Historien (Lücken füllen) → heutige Zeile → Nachrichten.
Danach entsteht die Ausgabe für alle Zertifikate aus den gespeicherten Daten.
--neu-bauen: ohne Netz, nur Auswertung und Ausgabe.  --isin: nur dieses Zertifikat abrufen.
Ein Fehler bei einem Zertifikat hält die anderen nicht auf (Exit 1, wenn eines fehlschlug).
Alle Pfade liegen relativ zur Projektwurzel (läuft so auch auf dem GitHub-Runner).
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tracker import daten as daten_modul
from tracker import excel, konfig, nachrichten, onvista, seite, speicher
from tracker.konfig import ConfigFehler

WURZEL = Path(__file__).resolve().parent
BERLIN = ZoneInfo("Europe/Berlin")
NEWS_PAUSE_S = 1.5
ZERT_PAUSE_S = 3.0   # Abstand zwischen zwei Zertifikaten, schont onvista
EXIT_OK, EXIT_ABRUF, EXIT_CONFIG = 0, 1, 2


def lade_config(pfad):
    return konfig.lade_config(pfad)


def _zeit_letzter_abruf(meta):
    try:
        zeit = datetime.fromisoformat(meta["abruf"]["zeit"])
    except (KeyError, TypeError, ValueError):
        return None
    return zeit if zeit.tzinfo else None


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


def _ordner(wurzel, z):
    return wurzel / "daten" / z["isin"]


def _lies_status(ordner):
    s = speicher.lies_meta(ordner / "status.json")
    return bool(s.get("ok", True)), str(s.get("meldung") or "")


def verarbeite(z, wurzel, jetzt, kw, schlafen):
    """Ein Zertifikat abrufen und speichern. Rückgabe "erledigt", "abgerufen" oder "fehler"."""
    heute, ordner = jetzt.date(), _ordner(wurzel, z)
    rows, meta = speicher.lies_kurse(ordner / "kurse.csv"), speicher.lies_meta(ordner / "meta.json")
    if heute > daten_modul.lauf_ende(z):
        print(f"{z['isin']}: Laufende erreicht ({daten_modul.lauf_ende(z)}). Keine Abrufe mehr.")
        return "erledigt"
    if schon_erledigt(rows, meta, heute):
        print(f"{z['isin']}: heute schon abgerufen.")
        return "erledigt"
    ok, meldung = True, ""
    try:
        rows, meta, meldung = abruf(z, rows, jetzt, **kw)
        speicher.schreibe_kurse(ordner / "kurse.csv", rows)
        speicher.schreibe_meta(ordner / "meta.json", meta)
        fetch = lambda url: onvista.hole_bytes(url, max_bytes=nachrichten.MAX_RSS_BYTES, **kw)  # noqa: E731
        hole_nachrichten(z, meta, rows, ordner / "nachrichten.jsonl", heute, fetch, schlafen)
    except onvista.AbrufFehler as e:
        ok, meldung = False, str(e)
    except Exception as e:  # bewusst breit: Das Dashboard darf nie "alles gut" zeigen, wenn der Lauf kaputt ist
        ok, meldung = False, f"Unerwarteter Fehler beim Abruf ({type(e).__name__})."
    if not ok:
        print(f"{z['isin']}: Fehler beim Abruf: {meldung}")
    speicher.schreibe_json(ordner / "status.json",
                           {"ok": ok, "meldung": meldung, "letzter_lauf": jetzt.isoformat(timespec="seconds")})
    return "abgerufen" if ok else "fehler"


def _daten_je_zertifikat(z, wurzel, jetzt):
    ordner = _ordner(wurzel, z)
    rows, meta = speicher.lies_kurse(ordner / "kurse.csv"), speicher.lies_meta(ordner / "meta.json")
    ok, meldung = _lies_status(ordner)
    return daten_modul.baue_daten(z, meta, rows, speicher.lies_nachrichten(ordner / "nachrichten.jsonl"), jetzt,
                                  ok, meldung, _zeit_letzter_abruf(meta))


def erzeuge_ausgabe(cfg, jetzt, wurzel):
    aus = wurzel / "ausgabe"
    g = daten_modul.baue_gesamt([_daten_je_zertifikat(z, wurzel, jetzt) for z in cfg["zertifikate"]])
    g["repo"], g["konfig"] = cfg.get("repo"), fingerabdruck(cfg)
    speicher.schreibe_json(aus / "daten.json", g)
    speicher.schreibe_json(aus / "status.json", g["status"])
    try:
        excel.schreibe_gesamt(g, aus / "kurse.xlsx")
    except Exception as e:  # bewusst breit: Excel ist Beiwerk, Dashboard und Status sollen trotzdem entstehen
        print(f"Hinweis: kurse.xlsx konnte nicht geschrieben werden ({type(e).__name__}); ist die Datei geöffnet?")
    seite_ok, seite_meldung = seite.rendere(g, wurzel / "tracker" / "vorlage.html", aus / "index.html")
    if not seite_ok:
        print("Hinweis:", seite_meldung)
    return g


def fingerabdruck(cfg):
    """Ändert sich, sobald sich irgendetwas an config.json ändert (Zertifikate, Wochen, Schwellen, Repo)."""
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _ausgabe_passt(wurzel, cfg):
    return speicher.lies_meta(wurzel / "ausgabe" / "daten.json").get("konfig") == fingerabdruck(cfg)


def _abrufen(ziele, wurzel, jetzt, kw, schlafen):
    ergebnisse = []
    for z in ziele:
        if "abgerufen" in ergebnisse or "fehler" in ergebnisse:
            schlafen(ZERT_PAUSE_S)
        ergebnisse.append(verarbeite(z, wurzel, jetzt, kw, schlafen))
    return ergebnisse


def main(argv=None, *, jetzt=None, oeffnen=None, schlafen=time.sleep, wurzel=WURZEL):
    p = argparse.ArgumentParser(description="Täglicher Kursspeicher für Discount-Zertifikate")
    p.add_argument("--neu-bauen", action="store_true", help="ohne Netz nur Auswertung und Ausgabe neu bauen")
    p.add_argument("--isin", help="nur dieses Zertifikat abrufen (muss in config.json stehen)")
    args = p.parse_args(argv)
    try:
        cfg = lade_config(wurzel / "config.json")
        ziele = [z for z in cfg["zertifikate"] if args.isin in (None, z["isin"])]
        if not ziele:
            raise ConfigFehler(f"{args.isin} steht nicht in config.json.")
    except ConfigFehler as e:
        print(f"Fehler: {e}")
        return EXIT_CONFIG
    jetzt = jetzt or datetime.now(BERLIN)
    ergebnisse = [] if args.neu_bauen else _abrufen(ziele, wurzel, jetzt, {"oeffnen": oeffnen, "schlafen": schlafen},
                                                    schlafen)
    if args.neu_bauen:
        print("Neu bauen ohne Netz.")
    elif all(e == "erledigt" for e in ergebnisse) and _ausgabe_passt(wurzel, cfg):
        print("Heute schon abgerufen. Kein neuer Abruf.")
        return EXIT_OK
    try:
        erzeuge_ausgabe(cfg, jetzt, wurzel)
    except Exception as e:  # bewusst breit: siehe verarbeite
        meldung = f"Unerwarteter Fehler in der Auswertung ({type(e).__name__})."
        print(meldung)
        speicher.schreibe_json(wurzel / "ausgabe" / "status.json",
                               {"ok": False, "meldung": meldung, "letzter_lauf": jetzt.isoformat(timespec="seconds")})
        return EXIT_ABRUF
    print(f"Fertig: {len(cfg['zertifikate'])} Zertifikate, {ergebnisse.count('abgerufen')} abgerufen.")
    return EXIT_ABRUF if "fehler" in ergebnisse else EXIT_OK


if __name__ == "__main__":
    for strom in (sys.stdout, sys.stderr):
        strom.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
