"""Baut daten.json (Vertrag zwischen Logik und Dashboard) aus Kursen, Analyse und Nachrichten."""
import math
from datetime import date, timedelta

from tracker import analyse, nachrichten, speicher

VORLAUF_TAGE = 30        # Quelle: SPEC.md, daten.json ("höchstens 30 Kalendertage anzeigen")
RUNDEN = 6
# Kurssprung-Schwellen in % je Tag, etwa 2- bis 4-fache Tagesschwankung.
# Quelle: eigene kurse.csv 12.08.–12.11.2026, Std.-Abw. der Tagesrenditen: Zertifikat 0,25 %, SAP 1,82 %, DAX 0,86 %.
# Überschreibbar in config.json ("sprung_pct").
SPRUNG_PCT = {"z": 2.0, "basis": 5.0, "dax": 3.0}
SPRUNG_FELD = {"z": "z_pct", "basis": "basis_pct", "dax": "dax_pct"}
EPS = 1e-9
EXTRA_FELDER = ("effekt_basis", "aktie_spez_pct", "cap_abstand_pct", "delta_geschaetzt", "beta_geschaetzt")


def lauf_start(config):
    return date.fromisoformat(config["start"])


def lauf_ende(config):
    return lauf_start(config) + timedelta(days=config["wochen"] * 7 - 1)


def _r(x):
    return round(x, RUNDEN) if isinstance(x, float) and math.isfinite(x) else x


def sprung_schwellen(config):
    return {**SPRUNG_PCT, **(config.get("sprung_pct") or {})}


def _spruenge(a, schwellen, basis_name):
    namen = {"z": "Zertifikat", "basis": basis_name or "Basiswert", "dax": "DAX"}
    erg = []
    for k, feld in SPRUNG_FELD.items():
        x = a.get(feld)
        if isinstance(x, float) and math.isfinite(x) and abs(x) >= schwellen[k] - EPS:
            erg.append({"wert": namen[k], "pct": _r(x), "schwelle": schwellen[k]})
    return erg


def _tag(row, a, start, news, verdikt):
    d = row["datum"]
    t = {"datum": d, "phase": "lauf" if date.fromisoformat(d) >= start else "vorlauf"}
    for k in ("z_geld", "z_brief", "z_quelle", "basis", "dax"):
        t[k] = row[k]
    for k in ("z_pct", "basis_pct", "dax_pct", "dz", "delta", "beta", "effekt_markt", "effekt_aktie", "effekt_zeit",
              "effekt_rest", "haupttreiber", "auffaellig", "z_score"):
        t[k] = _r(a[k])
    t.update(text=a["text"], verdikt=verdikt, nachrichten=news)
    for k in EXTRA_FELDER:
        t[k] = _r(a[k])
    t["theta_tag"], t["iv"] = row["theta_tag"], row["iv"]
    return t


def _fortschritt(config, jetzt):
    gesamt = config["wochen"] * 7
    tag = min(max((jetzt.date() - lauf_start(config)).days + 1, 0), gesamt)
    return {"tag": tag, "tage_gesamt": gesamt, "woche": math.ceil(tag / 7)}


def _produkt(config, meta):
    p = meta.get("produkt", {})
    return {"isin": p.get("isin") or config["isin"], "wkn": p.get("wkn"), "name": p.get("name"),
            "emittent": p.get("emittent"), "cap": p.get("cap"), "bezug": p.get("bezug", 1.0),
            "faellig": p.get("faellig"), "basis_name": p.get("basis_name"), "basis_isin": p.get("basis_isin"),
            "demo": bool(config.get("demo")), "lauf_start": config["start"], "lauf_ende": lauf_ende(config).isoformat(),
            "sprung_pct": sprung_schwellen(config)}


def _seit_start(rows, start):
    """Entwicklung vom letzten Schluss vor dem Start bis zum letzten bekannten Kurs."""
    davor = [rows[d] for d in sorted(rows) if date.fromisoformat(d) < start]
    alle = [rows[d] for d in sorted(rows)]
    ref = next((r for r in reversed(davor) if r["z_geld"] is not None), None)
    im_lauf = any(r["z_geld"] is not None for r in alle if date.fromisoformat(r["datum"]) >= start)
    if ref is None or not im_lauf:
        return {"bezug_datum": None, "z_eur": None, "z_pct": None, "basis_pct": None, "dax_pct": None}
    jetzt = {k: speicher._letzter(alle, k) for k in speicher.KURSE}
    basis_ref, dax_ref = speicher._letzter(davor, "basis"), speicher._letzter(davor, "dax")
    return {"bezug_datum": ref["datum"], "z_eur": jetzt["z_geld"] - ref["z_geld"],
            "z_pct": speicher._pct_aenderung(jetzt["z_geld"], ref["z_geld"]),
            "basis_pct": speicher._pct_aenderung(jetzt["basis"], basis_ref),
            "dax_pct": speicher._pct_aenderung(jetzt["dax"], dax_ref)}


def _aktuell(rows, meta, produkt):
    letzte = next((rows[d] for d in sorted(rows, reverse=True) if rows[d]["z_geld"] is not None), None)
    k = meta.get("kennzahlen", {})
    z = letzte or {}
    return {"z_geld": z.get("z_geld"), "z_brief": z.get("z_brief"), "max_ertrag_eur": k.get("max_ertrag_eur"),
            "max_ertrag_pct": k.get("max_ertrag_pct"), "delta": z.get("delta"), "discount_pct": k.get("discount_pct"),
            "cap_abstand_pct": analyse.cap_abstand_pct(z.get("basis"), produkt["cap"]),
            "seit_start": {k: _r(v) for k, v in _seit_start(rows, date.fromisoformat(produkt["lauf_start"])).items()}}


def tage_mit_analyse(config, meta, rows, news_roh):
    """Analyse über alle Zeilen, Rückgabe der anzuzeigenden Tage (Vorlauf begrenzt)."""
    produkt = _produkt(config, meta)
    liste = [rows[d] for d in sorted(rows)]
    ana = analyse.analysiere(liste, produkt["bezug"], produkt["cap"], produkt["basis_name"])
    start = lauf_start(config)
    grenze = start - timedelta(days=VORLAUF_TAGE)
    erg = []
    for row, a in zip(liste, ana):
        if date.fromisoformat(row["datum"]) < grenze:
            continue
        news = nachrichten.bewerte(news_roh.get(row["datum"], []), a, produkt["basis_name"]) if a["dz"] is not None else []
        t = _tag(row, a, start, news, nachrichten.verdikt(a, news))
        t["spruenge"] = _spruenge(a, sprung_schwellen(config), produkt["basis_name"])
        erg.append(t)
    return erg


def baue_daten(config, meta, rows, news_roh, jetzt, ok, meldung, stand_zeit=None):
    """jetzt bestimmt den Fortschritt; stand_zeit (Zeit des letzten Abrufs) den angezeigten Stand."""
    produkt = _produkt(config, meta)
    stand = (stand_zeit or jetzt).isoformat(timespec="seconds")
    wochen = [{k: _r(v) for k, v in w.items()} for w in speicher.wochenschnitte(rows, lauf_start(config))]
    return {
        "stand": stand, "produkt": produkt, "aktuell": _aktuell(rows, meta, produkt),
        "fortschritt": _fortschritt(config, jetzt), "tage": tage_mit_analyse(config, meta, rows, news_roh),
        "wochen": wochen, "status": {"ok": ok, "meldung": meldung, "letzter_lauf": stand},
    }
