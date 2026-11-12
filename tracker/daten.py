"""Baut daten.json (Vertrag zwischen Logik und Dashboard) aus Kursen, Analyse und Nachrichten."""
import math
from datetime import date, timedelta

from tracker import analyse, nachrichten, speicher

VORLAUF_TAGE = 30        # Quelle: SPEC.md, daten.json ("höchstens 30 Kalendertage anzeigen")
RUNDEN = 6
EXTRA_FELDER = ("effekt_basis", "aktie_spez_pct", "cap_abstand_pct", "delta_geschaetzt", "beta_geschaetzt")


def lauf_start(config):
    return date.fromisoformat(config["start"])


def lauf_ende(config):
    return lauf_start(config) + timedelta(days=config["wochen"] * 7 - 1)


def _r(x):
    return round(x, RUNDEN) if isinstance(x, float) and math.isfinite(x) else x


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
            "demo": bool(config.get("demo")), "lauf_start": config["start"], "lauf_ende": lauf_ende(config).isoformat()}


def _aktuell(rows, meta, produkt):
    letzte = next((rows[d] for d in sorted(rows, reverse=True) if rows[d]["z_geld"] is not None), None)
    k = meta.get("kennzahlen", {})
    z = letzte or {}
    return {"z_geld": z.get("z_geld"), "z_brief": z.get("z_brief"), "max_ertrag_eur": k.get("max_ertrag_eur"),
            "max_ertrag_pct": k.get("max_ertrag_pct"), "delta": z.get("delta"), "discount_pct": k.get("discount_pct"),
            "cap_abstand_pct": analyse.cap_abstand_pct(z.get("basis"), produkt["cap"])}


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
        erg.append(_tag(row, a, start, news, nachrichten.verdikt(a, news)))
    return erg


def baue_daten(config, meta, rows, news_roh, jetzt, ok, meldung):
    produkt = _produkt(config, meta)
    stand = jetzt.isoformat(timespec="seconds")
    wochen = [{k: _r(v) for k, v in w.items()} for w in speicher.wochenschnitte(rows, lauf_start(config))]
    return {
        "stand": stand, "produkt": produkt, "aktuell": _aktuell(rows, meta, produkt),
        "fortschritt": _fortschritt(config, jetzt), "tage": tage_mit_analyse(config, meta, rows, news_roh),
        "wochen": wochen, "status": {"ok": ok, "meldung": meldung, "letzter_lauf": stand},
    }
