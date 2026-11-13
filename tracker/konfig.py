"""config.json lesen, prüfen und ändern. Ein Zertifikat (altes Format) oder eine Liste (neues Format).

Neues Format:
    {"repo": "besitzer/name", "sprung_pct": {"z": 2, "basis": 5, "dax": 3},
     "zertifikate": [{"isin": "...", "start": "YYYY-MM-DD", "wochen": 10, "demo": false,
                      "basis_suchbegriff": null, "sprung_pct": {...}}]}
"""
import json
import re
from datetime import date
from pathlib import Path

ISIN_MUSTER = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
REPO_MUSTER = re.compile(r"^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$")  # GitHub besitzer/name, für die Issue-Links
MAX_ZERTIFIKATE = 10      # begrenzt die Abrufe bei onvista je Tag
STANDARD_WOCHEN = 10
SPRUNG_SCHLUESSEL = ("z", "basis", "dax")


class ConfigFehler(Exception):
    pass


def _pruefe_sprung(s):
    """Optional {"z"|"basis"|"dax": Prozent > 0 und <= 100}."""
    if s is None:
        return {}
    gueltig = isinstance(s, dict) and all(
        k in SPRUNG_SCHLUESSEL and isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= 100
        for k, v in s.items())
    if not gueltig:
        raise ConfigFehler('config.json: sprung_pct muss z. B. {"z": 2, "basis": 5, "dax": 3} sein (Prozent, größer 0).')
    return {k: float(v) for k, v in s.items()}


def isin_pruefziffer_ok(isin):
    """Luhn über die Ziffernfolge (Buchstaben A=10 … Z=35), wie bei jeder echten ISIN."""
    if not (isinstance(isin, str) and ISIN_MUSTER.match(isin)):
        return False
    ziffern = "".join(str(int(c, 36)) for c in isin)
    summe = 0
    for i, z in enumerate(reversed(ziffern)):
        n = int(z) * (2 if i % 2 else 1)
        summe += n - 9 if n > 9 else n
    return summe % 10 == 0


def pruefe_isin(isin):
    if not (isinstance(isin, str) and ISIN_MUSTER.match(isin)):
        raise ConfigFehler("config.json: isin ist keine gültige ISIN.")
    return isin


def _pruefe_repo(repo):
    if repo is None:
        return None
    if not (isinstance(repo, str) and REPO_MUSTER.match(repo) and ".." not in repo):
        raise ConfigFehler('config.json: repo muss "besitzer/name" sein.')
    return repo


def _eintrag(c, sprung_global):
    pruefe_isin(c["isin"])
    date.fromisoformat(c["start"])
    if not (isinstance(c["wochen"], int) and not isinstance(c["wochen"], bool) and 1 <= c["wochen"] <= 52):
        raise ConfigFehler("config.json: wochen muss eine Zahl von 1 bis 52 sein.")
    begriff = c.get("basis_suchbegriff")
    if begriff is not None and not (isinstance(begriff, str) and 0 < len(begriff) <= 100):
        raise ConfigFehler("config.json: basis_suchbegriff muss null oder ein kurzer Text sein.")
    return {"isin": c["isin"], "demo": bool(c.get("demo", False)), "start": c["start"], "wochen": c["wochen"],
            "basis_suchbegriff": begriff, "sprung_pct": {**sprung_global, **_pruefe_sprung(c.get("sprung_pct"))}}


def pruefe(roh):
    """Rohes JSON-Objekt → {"sprung_pct": {...}, "zertifikate": [...]}; wirft ConfigFehler."""
    if not isinstance(roh, dict):
        raise ConfigFehler("config.json muss ein Objekt sein.")
    if "zertifikate" not in roh:  # altes Einzelformat
        e = _eintrag(roh, {})
        return {"repo": _pruefe_repo(roh.get("repo")), "sprung_pct": e["sprung_pct"],
                "zertifikate": [{**e, "sprung_pct": dict(e["sprung_pct"])}]}
    liste = roh["zertifikate"]
    if not (isinstance(liste, list) and 1 <= len(liste) <= MAX_ZERTIFIKATE):
        raise ConfigFehler(f"config.json: zertifikate muss eine Liste mit 1 bis {MAX_ZERTIFIKATE} Einträgen sein.")
    sprung = _pruefe_sprung(roh.get("sprung_pct"))
    eintraege = [_eintrag(c, sprung) for c in liste]
    if len({e["isin"] for e in eintraege}) != len(eintraege):
        raise ConfigFehler("config.json: jede ISIN darf nur einmal vorkommen.")
    return {"repo": _pruefe_repo(roh.get("repo")), "sprung_pct": sprung, "zertifikate": eintraege}


def lade_config(pfad):
    try:
        return pruefe(json.loads(Path(pfad).read_text(encoding="utf-8")))
    except ConfigFehler:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise ConfigFehler("config.json fehlt oder ist unlesbar (nötig: isin, start, wochen).") from None


def _roh(c):
    """Zurück ins Dateiformat; eigene Schwellen nur, wenn sie von den globalen abweichen."""
    g = c["sprung_pct"]
    aus = []
    for z in c["zertifikate"]:
        e = {k: z[k] for k in ("isin", "start", "wochen", "demo", "basis_suchbegriff")}
        eigen = {k: v for k, v in z["sprung_pct"].items() if g.get(k) != v}
        if eigen:
            e["sprung_pct"] = eigen
        aus.append(e)
    kopf = {"repo": c["repo"]} if c.get("repo") else {}
    return {**kopf, "sprung_pct": g, "zertifikate": aus}


def schreibe_config(pfad, c):
    Path(pfad).write_text(json.dumps(_roh(c), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mit_zertifikat(c, isin, start):
    """Neue Config mit zusätzlichem Zertifikat (Eingabe bleibt unverändert)."""
    pruefe_isin(isin)
    if any(z["isin"] == isin for z in c["zertifikate"]):
        raise ConfigFehler(f"{isin} wird schon verfolgt.")
    if len(c["zertifikate"]) >= MAX_ZERTIFIKATE:
        raise ConfigFehler(f"Höchstens {MAX_ZERTIFIKATE} Zertifikate. Erst eines entfernen.")
    neu = {"isin": isin, "demo": False, "start": start, "wochen": STANDARD_WOCHEN, "basis_suchbegriff": None,
           "sprung_pct": dict(c["sprung_pct"])}
    return {**c, "sprung_pct": dict(c["sprung_pct"]), "zertifikate": [dict(z) for z in c["zertifikate"]] + [neu]}


def ohne_zertifikat(c, isin):
    pruefe_isin(isin)
    rest = [dict(z) for z in c["zertifikate"] if z["isin"] != isin]
    if len(rest) == len(c["zertifikate"]):
        raise ConfigFehler(f"{isin} wird nicht verfolgt.")
    if not rest:
        raise ConfigFehler("Das letzte Zertifikat kann nicht entfernt werden.")
    return {**c, "sprung_pct": dict(c["sprung_pct"]), "zertifikate": rest}
