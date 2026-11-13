"""Schreibt ausgabe/kurse.xlsx (Tageskurse, Wochenschnitte, Erklärungen, Info) mit nativen Diagrammen."""
import re
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

SCHRIFT = "Arial"
# Excel zeigt diese US-Formatcodes je nach Systemsprache mit deutschem Komma und Punkt an.
FMT_DATUM, FMT_KURS, FMT_PCT = "DD.MM.YYYY", "#,##0.00", "0.00%"
KOPF_FUELLUNG = PatternFill("solid", fgColor="1F3A5F")
STEUERZEICHEN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
QUELLE = "onvista.de (api.onvista.de), Schlagzeilen: Google News RSS"


def _text(wert):
    return STEUERZEICHEN.sub("", str(wert))


def _zelle(ws, zeile, spalte, wert, fmt=None):
    c = ws.cell(zeile, spalte)
    if isinstance(wert, str):
        c.value = _text(wert)
        c.data_type = "s"   # nie als Formel auslegen, auch wenn eine Schlagzeile mit "=" beginnt
    else:
        c.value = wert
    c.font = Font(name=SCHRIFT, size=10)
    if fmt:
        c.number_format = fmt
    return c


def _kopf(ws, titel, breiten):
    for i, (t, b) in enumerate(zip(titel, breiten), start=1):
        c = ws.cell(1, i, t)
        c.font = Font(name=SCHRIFT, size=10, bold=True, color="FFFFFF")
        c.fill = KOPF_FUELLUNG
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = b
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(titel))}1"


def _filter_bis(ws, n_zeilen):
    ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}{max(n_zeilen + 1, 2)}"


def _pct(x):
    return None if x is None else x / 100


def _datum(text):
    return datetime.combine(date.fromisoformat(text), datetime.min.time())


def _diagramm(ws, titel, spalte, n, kat_spalte, anker):
    if n < 1:
        return
    ch = LineChart()
    ch.title, ch.height, ch.width = titel, 8, 18
    ch.y_axis.title, ch.y_axis.number_format = "Euro", FMT_KURS
    ch.x_axis.number_format = FMT_DATUM if kat_spalte == 1 else "General"
    ch.y_axis.delete = ch.x_axis.delete = False
    ch.add_data(Reference(ws, min_col=spalte, min_row=1, max_row=n + 1), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=kat_spalte, min_row=2, max_row=n + 1))
    ws.add_chart(ch, anker)


def _tageskurse(wb, d):
    ws = wb.active
    ws.title = "Tageskurse"
    _kopf(ws, ["Datum", "Zertifikat Geld", "Zertifikat Brief", "Basiswert", "DAX", "Zertifikat %", "Basiswert %", "DAX %", "Phase", "Kurssprung"],
          [12, 15, 15, 12, 12, 13, 13, 11, 10, 24])
    for i, t in enumerate(d["tage"], start=2):
        _zelle(ws, i, 1, _datum(t["datum"]), FMT_DATUM)
        for sp, k in ((2, "z_geld"), (3, "z_brief"), (4, "basis"), (5, "dax")):
            _zelle(ws, i, sp, t[k], FMT_KURS)
        for sp, k in ((6, "z_pct"), (7, "basis_pct"), (8, "dax_pct")):
            _zelle(ws, i, sp, _pct(t[k]), FMT_PCT)
        _zelle(ws, i, 9, t["phase"])
        _zelle(ws, i, 10, sprung_text(t.get("spruenge")))
    _filter_bis(ws, len(d["tage"]))
    _diagramm(ws, "Zertifikat (Geldkurs)", 2, len(d["tage"]), 1, "L2")


def sprung_text(spruenge):
    """[{wert, pct}] → "SAP −6,1 %, DAX +3,2 %" (deutsches Format, echtes Minuszeichen)."""
    teile = []
    for s in spruenge or []:
        pct = s.get("pct")
        if isinstance(pct, (int, float)):
            zahl = f"{abs(pct):.1f}".replace(".", ",")
            teile.append(f"{s.get('wert', '')} {'+' if pct > 0 else '−'}{zahl} %")
    return ", ".join(teile) or None


WOCHEN_KURSE = (("z", "Zertifikat"), ("basis", "Basiswert"), ("dax", "DAX"))


def _wochen(wb, d):
    ws = wb.create_sheet("Wochenschnitte")
    kopf = ["Woche", "Von", "Bis", "Tage"]
    for _, name in WOCHEN_KURSE:
        kopf += [f"{name} Schluss", f"{name} Woche", f"{name} Schnitt"]
    _kopf(ws, kopf + ["Schnitt zur Vorwoche", "Hinweis"], [11, 12, 12, 7] + [16, 13, 16] * 3 + [20, 22])
    for i, w in enumerate(d["wochen"], start=2):
        _zelle(ws, i, 1, w["woche"])
        _zelle(ws, i, 2, _datum(w["von"]), FMT_DATUM)
        _zelle(ws, i, 3, _datum(w["bis"]), FMT_DATUM)
        _zelle(ws, i, 4, w["tage"])
        for j, (k, _) in enumerate(WOCHEN_KURSE):
            sp = 5 + 3 * j
            _zelle(ws, i, sp, w.get(f"{k}_schluss"), FMT_KURS)
            _zelle(ws, i, sp + 1, _pct(w.get(f"{k}_woche_pct")), FMT_PCT)
            _zelle(ws, i, sp + 2, w.get(f"{k}_schnitt"), FMT_KURS)
        _zelle(ws, i, 14, _pct(w["z_vorwoche_pct"]), FMT_PCT)
        _zelle(ws, i, 15, "unvollständige Woche" if w.get("unvollstaendig") else "")
    _filter_bis(ws, len(d["wochen"]))
    _diagramm(ws, "Wochenschluss Zertifikat", 5, len(d["wochen"]), 1, "Q2")


def _erklaerungen(wb, d):
    ws = wb.create_sheet("Erklärungen")
    _kopf(ws, ["Datum", "Erklärung", "Einordnung", "Wichtigste Schlagzeile"], [12, 90, 26, 60])
    for i, t in enumerate(d["tage"], start=2):
        _zelle(ws, i, 1, _datum(t["datum"]), FMT_DATUM)
        _zelle(ws, i, 2, t["text"] or "").alignment = Alignment(wrap_text=True, vertical="top")
        _zelle(ws, i, 3, t["verdikt"] or "")
        n = t["nachrichten"][0] if t["nachrichten"] else None
        _zelle(ws, i, 4, f"{n['titel']} ({n['quelle'] or 'Quelle unbekannt'})" if n else "")
    _filter_bis(ws, len(d["tage"]))


def _info(wb, d):
    ws = wb.create_sheet("Info")
    p = d["produkt"]
    zeilen = [("ISIN", p["isin"]), ("WKN", p["wkn"]), ("Name", p["name"]), ("Emittent", p["emittent"]),
              ("Cap", p["cap"]), ("Bezugsverhältnis", p["bezug"]), ("Fällig am", p["faellig"]),
              ("Basiswert", p["basis_name"]), ("Basiswert ISIN", p["basis_isin"]),
              ("Laufstart", p["lauf_start"]), ("Laufende", p["lauf_ende"]), ("Demo", "ja" if p["demo"] else "nein"),
              ("Quelle", QUELLE), ("Abrufzeit", d["stand"]),
              ("Hinweis", "Schlagzeilen zeigen einen zeitlichen Zusammenhang, keinen Beweis.")]
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 20, 80
    for i, (k, v) in enumerate(zeilen, start=1):
        _zelle(ws, i, 1, k).font = Font(name=SCHRIFT, size=10, bold=True)
        _zelle(ws, i, 2, "" if v is None else v)


def schreibe(d, pfad):
    wb = Workbook()
    _tageskurse(wb, d)
    _wochen(wb, d)
    _erklaerungen(wb, d)
    _info(wb, d)
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    wb.save(pfad)
