"""Lesen, Zusammenführen und Schreiben der Tagesdaten (CSV, JSON, JSONL) und Wochenschnitte."""
import csv
import io
import json
import math
import os
import tempfile
from datetime import date
from pathlib import Path

SPALTEN = ("datum", "z_geld", "z_brief", "z_quelle", "basis", "dax", "delta", "theta_tag", "iv")
ZAHLEN = ("z_geld", "z_brief", "basis", "dax", "delta", "theta_tag", "iv")
VOLLSTAENDIG_FELDER = ("z_geld", "z_brief", "basis", "dax")
# Eine ISO-Kalenderwoche mit weniger Handelstagen gilt als unvollständig (Feiertage, Start mitten in der Woche).
VOLLE_WOCHE_TAGE = 5


def _leer_zeile(datum):
    z = {c: None for c in SPALTEN}
    z["datum"] = datum
    return z


def _zahl(text):
    try:
        z = float(text) if text not in (None, "") else None
    except ValueError:
        return None
    return z if z is None or math.isfinite(z) else None


def _kurs(text):
    z = _zahl(text)
    return z if z is not None and z > 0 else None


def _datum_ok(text):
    try:
        date.fromisoformat(text)
        return True
    except (TypeError, ValueError):
        return False


def lies_kurse(pfad):
    """kurse.csv → {datum: Zeile}. Fehlende Datei = leer; ungültige Zeilen werden übersprungen."""
    pfad = Path(pfad)
    if not pfad.exists():
        return {}
    rows = {}
    with pfad.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if not _datum_ok(r.get("datum")):
                continue
            z = _leer_zeile(r["datum"])
            for c in ZAHLEN:
                z[c] = (_kurs if c in VOLLSTAENDIG_FELDER else _zahl)(r.get(c))
            z["z_quelle"] = r.get("z_quelle") or None
            rows[r["datum"]] = z
    return rows


def _atomar_schreiben(pfad, inhalt):
    """Schreibt nur bei Änderung. Rückgabe: True, wenn geschrieben wurde."""
    pfad = Path(pfad)
    if pfad.exists() and pfad.read_bytes() == inhalt:
        return False
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=pfad.parent, prefix=pfad.name + ".")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(inhalt)
        os.replace(tmp, pfad)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)   # sonst würde die Restdatei mit committet
        raise
    return True


def schreibe_kurse(pfad, rows):
    puffer = io.StringIO(newline="")
    w = csv.writer(puffer, lineterminator="\n")
    w.writerow(SPALTEN)
    for d in sorted(rows):
        z = rows[d]
        w.writerow(["" if z.get(c) is None else repr(z[c]) if c in ZAHLEN else z[c] for c in SPALTEN])
    return _atomar_schreiben(pfad, puffer.getvalue().encode("utf-8"))


def ist_vollstaendig(z):
    return bool(z) and z.get("z_quelle") == "snapshot" and all(z.get(c) is not None for c in VOLLSTAENDIG_FELDER)


def _kopie(rows):
    return {d: dict(z) for d, z in rows.items()}


def _fuelle(z, werte):
    for c, v in werte.items():
        if v is not None and z.get(c) is None:
            z[c] = v


def fuelle_historie(rows, hist):
    """Schlusskurse der Historie eintragen. Vorhandene Werte bleiben unangetastet."""
    neu = _kopie(rows)
    for feld, quelle in (("z_geld", "z"), ("basis", "basis"), ("dax", "dax")):
        for d, kurs in hist.get(quelle, {}).items():
            z = neu.setdefault(d, _leer_zeile(d))
            if z[feld] is None:
                z[feld] = kurs
                if feld == "z_geld":
                    z["z_quelle"] = "historie"
    return neu


def fuelle_snapshot(rows, datum, werte):
    """Werte des Snapshots in die Zeile des Handelstags eintragen (nur Leeres)."""
    neu = _kopie(rows)
    z = neu.setdefault(datum, _leer_zeile(datum))
    hatte_z = z["z_geld"] is not None
    _fuelle(z, {c: werte.get(c) for c in ZAHLEN})
    if z["z_geld"] is not None and not hatte_z:
        z["z_quelle"] = "snapshot"
    elif z["z_quelle"] is None and z["z_brief"] is not None:
        z["z_quelle"] = "snapshot"
    return neu


def lies_meta(pfad):
    pfad = Path(pfad)
    if not pfad.exists():
        return {}
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def schreibe_json(pfad, obj):
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    return _atomar_schreiben(pfad, text.encode("utf-8"))


schreibe_meta = schreibe_json


def lies_nachrichten(pfad):
    """nachrichten.jsonl → {datum: [Nachricht,...]}. Ein Tag ohne Treffer steht mit leerer Liste drin."""
    pfad = Path(pfad)
    erg = {}
    if not pfad.exists():
        return erg
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        try:
            n = json.loads(zeile)
            d = n["datum"]
        except (ValueError, KeyError, TypeError):
            continue
        liste = erg.setdefault(d, [])
        if not n.get("leer"):
            liste.append({k: v for k, v in n.items() if k not in ("datum", "leer")})
    return erg


def haenge_nachrichten_an(pfad, datum, nachrichten):
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    zeilen = [dict(n, datum=datum) for n in nachrichten] or [{"datum": datum, "leer": True}]
    with pfad.open("a", encoding="utf-8", newline="\n") as f:
        for z in zeilen:
            f.write(json.dumps(z, ensure_ascii=False) + "\n")


def _schnitt(werte):
    werte = [w for w in werte if w is not None]
    return sum(werte) / len(werte) if werte else None


def wochenschnitte(rows, start):
    """ISO-Wochen ab start: Mittel von z_geld, basis, dax; tage; Änderung zur Vorwoche in %."""
    gruppen = {}
    for d in sorted(rows):
        dd = date.fromisoformat(d)
        if dd < start:
            continue
        j, w, _ = dd.isocalendar()
        gruppen.setdefault(f"{j}-W{w:02d}", []).append(rows[d])
    erg, vorher = [], None
    for name, zeilen in gruppen.items():
        z = _schnitt([r["z_geld"] for r in zeilen])
        tage = sum(1 for r in zeilen if r["z_geld"] is not None)
        erg.append({
            "woche": name, "von": zeilen[0]["datum"], "bis": zeilen[-1]["datum"], "tage": tage,
            "unvollstaendig": tage < VOLLE_WOCHE_TAGE,
            "z_schnitt": z, "basis_schnitt": _schnitt([r["basis"] for r in zeilen]),
            "dax_schnitt": _schnitt([r["dax"] for r in zeilen]),
            "z_vorwoche_pct": (z / vorher - 1) * 100 if z is not None and vorher else None,
        })
        if z is not None:
            vorher = z
    return erg
