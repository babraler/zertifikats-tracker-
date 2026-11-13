"""Zertifikat per Issue-Titel hinzufügen oder entfernen (läuft im Workflow "Zertifikat verwalten").

Titel (genau so, sonst passiert nichts):
    Zertifikat hinzufügen: <WKN oder ISIN>
    Zertifikat entfernen: <WKN oder ISIN>

Der Titel kommt aus der Umgebungsvariable ISSUE_TITLE (nie aus der Kommandozeile, damit die Shell ihn nie liest).
Die Antwort für den Issue-Kommentar landet in der Datei aus ANTWORT_DATEI.
Exit 0 = erledigt, 1 = abgelehnt oder Abruf gescheitert, 2 = Titel nicht erkannt.
"""
import contextlib
import io
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import lauf
from tracker import konfig, onvista, speicher
from tracker.konfig import ConfigFehler

WURZEL = Path(__file__).resolve().parent
TITEL_MUSTER = re.compile(r"^Zertifikat (hinzufügen|entfernen): ([A-Z0-9]{6}|[A-Z0-9]{12})$")
EXIT_OK, EXIT_ABGELEHNT, EXIT_TITEL = 0, 1, 2
MARKDOWN_ZEICHEN = re.compile(r"[\\`*_\[\]()<>#|!~@]")  # Name von onvista nur als schlichter Text ins Issue


class Abgelehnt(Exception):
    pass


isin_pruefziffer_ok = konfig.isin_pruefziffer_ok


def lies_titel(titel):
    """→ (aktion, art, kennung) oder None."""
    m = TITEL_MUSTER.match((titel or "").strip())
    if not m:
        return None
    aktion, kennung = m.groups()
    if len(kennung) == 12:
        return (aktion, "ISIN", kennung) if isin_pruefziffer_ok(kennung) else None
    return aktion, "WKN", kennung


def _still(funktion, *args, **kw):
    """lauf.main schreibt viel auf stdout; im Issue zählt nur das Ergebnis."""
    with contextlib.redirect_stdout(io.StringIO()) as out:
        code = funktion(*args, **kw)
    return code, out.getvalue()


def hinzufuegen(cfg, art, kennung, heute, kw):
    url = f"{onvista.BASIS_URL}/derivatives/{art}:{kennung}/snapshot"
    try:
        z = onvista.parse_zertifikat(onvista.hole_json(url, **kw))
    except onvista.DatenFehler as e:
        raise Abgelehnt(f"{kennung} ist bei onvista kein Discount-Zertifikat ({e}).") from None
    except onvista.AbrufFehler as e:
        raise Abgelehnt(f"onvista konnte {kennung} nicht liefern: {e}") from None
    isin = z.get("isin") or ""
    if not isin_pruefziffer_ok(isin):
        raise Abgelehnt(f"onvista liefert zu {kennung} keine gültige ISIN.")
    try:
        neu = konfig.mit_zertifikat(cfg, isin, heute.isoformat())
    except ConfigFehler as e:
        raise Abgelehnt(str(e)) from None
    return neu, isin, z


def _isin_zur_wkn(cfg, wkn, wurzel):
    for z in cfg["zertifikate"]:
        meta = speicher.lies_meta(wurzel / "daten" / z["isin"] / "meta.json")
        if (meta.get("produkt") or {}).get("wkn") == wkn:
            return z["isin"]
    raise Abgelehnt(f"{wkn} wird nicht verfolgt (oder hat noch keine Stammdaten; dann bitte mit der ISIN entfernen).")


def entfernen(cfg, art, kennung, wurzel):
    isin = kennung if art == "ISIN" else _isin_zur_wkn(cfg, kennung, wurzel)
    try:
        return konfig.ohne_zertifikat(cfg, isin), isin
    except ConfigFehler as e:
        raise Abgelehnt(str(e)) from None


def ausfuehren(titel, jetzt, kw, wurzel):
    """→ (exit_code, antworttext)."""
    gelesen = lies_titel(titel)
    if gelesen is None:
        return EXIT_TITEL, ("Titel nicht erkannt. Erlaubt ist genau `Zertifikat hinzufügen: <WKN oder ISIN>` "
                            "oder `Zertifikat entfernen: <WKN oder ISIN>` (Großbuchstaben, WKN 6 oder ISIN 12 Zeichen).")
    aktion, art, kennung = gelesen
    pfad = wurzel / "config.json"
    try:
        cfg = konfig.lade_config(pfad)
        if aktion == "hinzufügen":
            neu, isin, z = hinzufuegen(cfg, art, kennung, jetzt.date(), kw)
        else:
            neu, isin = entfernen(cfg, art, kennung, wurzel)
    except (Abgelehnt, ConfigFehler) as e:
        return EXIT_ABGELEHNT, f"Nicht ausgeführt: {e}"
    konfig.schreibe_config(pfad, neu)
    anzahl = len(neu["zertifikate"])
    if aktion == "entfernen":
        code, _ = _still(lauf.main, ["--neu-bauen"], jetzt=jetzt, wurzel=wurzel, **kw)
        return EXIT_OK, (f"{isin} wird nicht mehr verfolgt und ist aus der App entfernt. Die bisherigen Kurse bleiben "
                         f"unter `daten/{isin}/` gespeichert. Jetzt verfolgt: {anzahl}.")
    code, _ = _still(lauf.main, ["--isin", isin], jetzt=jetzt, wurzel=wurzel, **kw)
    name = MARKDOWN_ZEICHEN.sub("", str(z.get("name") or ""))[:120].strip() or isin
    text = (f"{name} ({isin}, WKN {z.get('wkn') or '–'}) ist aufgenommen. Beobachtung ab {jetzt.date():%d.%m.%Y}, "
            f"{konfig.STANDARD_WOCHEN} Wochen. Jetzt verfolgt: {anzahl}.")
    if (wurzel / "daten" / isin / "kurse.csv").exists() and code == lauf.EXIT_OK:
        text += " Frühere Kurse dieses Zertifikats werden weiterverwendet."
    if code != lauf.EXIT_OK:
        text += " Der erste Kursabruf hat nicht geklappt; der nächste tägliche Lauf versucht es erneut."
    return EXIT_OK, text + " Die App ist in etwa 2 Minuten aktualisiert."


def main(*, titel=None, antwort=None, jetzt=None, oeffnen=None, schlafen=time.sleep, wurzel=WURZEL):
    titel = os.environ.get("ISSUE_TITLE", "") if titel is None else titel
    antwort = Path(antwort or os.environ.get("ANTWORT_DATEI") or wurzel / "verwalten-antwort.md")
    jetzt = jetzt or datetime.now(lauf.BERLIN)
    code, text = ausfuehren(titel, jetzt, {"oeffnen": oeffnen, "schlafen": schlafen}, Path(wurzel))
    antwort.parent.mkdir(parents=True, exist_ok=True)
    antwort.write_text(text + "\n", encoding="utf-8")
    print(text)
    return code


if __name__ == "__main__":
    for strom in (sys.stdout, sys.stderr):
        strom.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
