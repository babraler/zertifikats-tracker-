"""Setzt daten.json in die Dashboard-Vorlage ein → ausgabe/index.html."""
import json
from pathlib import Path

from tracker.speicher import _atomar_schreiben

PLATZHALTER = "/*__DATEN__*/null"
# Diese Zeichen könnten ein <script> beenden oder JS-Zeilen brechen; als \uXXXX-Escape bleibt das JSON gültig.
MASKEN = {"<": "\\u003c", ">": "\\u003e", "&": "\\u0026", " ": "\\u2028", " ": "\\u2029"}


def daten_als_js(daten):
    text = json.dumps(daten, ensure_ascii=False, separators=(",", ":"))
    for zeichen, ersatz in MASKEN.items():
        text = text.replace(zeichen, ersatz)
    return text


def rendere(daten, vorlage, ziel):
    """Rückgabe (ok, meldung). Fehlt die Vorlage, gibt es eine klare Meldung und der Lauf geht weiter."""
    vorlage = Path(vorlage)
    if not vorlage.exists():
        return False, f"Vorlage {vorlage.name} fehlt (Pfad tracker/vorlage.html), index.html wurde nicht erzeugt."
    html = vorlage.read_text(encoding="utf-8")
    if PLATZHALTER not in html:
        return False, f"In {vorlage.name} fehlt der Platzhalter {PLATZHALTER}, index.html wurde nicht erzeugt."
    _atomar_schreiben(ziel, html.replace(PLATZHALTER, daten_als_js(daten), 1).encode("utf-8"))
    return True, ""
