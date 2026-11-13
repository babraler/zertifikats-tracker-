"""Tests für tracker/seite.py und tracker/excel.py."""
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl

from tracker import daten, excel, seite
from tracker.test_daten import CONFIG, META, rows

JETZT = datetime(2026, 11, 12, 18, 40, tzinfo=ZoneInfo("Europe/Berlin"))
BOESE = '</script><script>alert(1)</script> & "x" \u2028\u2029'


def beispiel():
    r = rows(date(2026, 10, 12), date(2026, 11, 12))
    roh = {"2026-11-12": [{"titel": "SAP hebt Prognose an " + BOESE, "quelle": "Q", "zeit": "2026-11-12T10:00:00+01:00", "url": "https://x.de"}]}
    return daten.baue_daten(CONFIG, META, r, roh, JETZT, True, "")


class TestSeite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.vorlage = self.dir / "vorlage.html"
        self.vorlage.write_text("<html><script>const DATEN = /*__DATEN__*/null;</script></html>", encoding="utf-8")
        self.ziel = self.dir / "ausgabe" / "index.html"

    def tearDown(self):
        self.tmp.cleanup()

    def test_platzhalter_wird_ersetzt_und_json_bleibt_gueltig(self):
        d = beispiel()
        ok, meldung = seite.rendere(d, self.vorlage, self.ziel)
        self.assertTrue(ok, meldung)
        html = self.ziel.read_text(encoding="utf-8")
        self.assertNotIn("/*__DATEN__*/null", html)
        eingebettet = html.split("const DATEN = ")[1].rsplit(";</script>", 1)[0]
        self.assertEqual(json.loads(eingebettet), d)

    def test_kein_skript_ausbruch(self):
        seite.rendere(beispiel(), self.vorlage, self.ziel)
        html = self.ziel.read_text(encoding="utf-8")
        self.assertEqual(html.count("</script>"), 1)
        for zeichen in ("\u2028", "\u2029"):
            self.assertNotIn(zeichen, html)
        self.assertIn("\\u003c/script\\u003e", html)
        self.assertIn("\\u0026", html)

    def test_app_dateien_landen_neben_der_seite(self):
        ok, _ = seite.rendere(beispiel(), self.vorlage, self.ziel)
        self.assertTrue(ok)
        for name in seite.APP_DATEIEN:
            self.assertTrue((self.ziel.parent / name).is_file(), name)
        self.assertNotIn("icons_erzeugen.py", seite.APP_DATEIEN)

    def test_echte_vorlage_bindet_app_ein(self):
        html = (Path(seite.__file__).parent / "vorlage.html").read_text(encoding="utf-8")
        for teil in ('rel="manifest" href="manifest.webmanifest"', 'rel="apple-touch-icon"', "serviceWorker.register('sw.js')"):
            self.assertIn(teil, html)

    def test_fehlende_vorlage_meldet_klar_und_wirft_nicht(self):
        ok, meldung = seite.rendere(beispiel(), self.dir / "gibt-es-nicht.html", self.ziel)
        self.assertFalse(ok)
        self.assertIn("vorlage.html", meldung)
        self.assertFalse(self.ziel.exists())

    def test_vorlage_ohne_platzhalter(self):
        self.vorlage.write_text("<html></html>", encoding="utf-8")
        ok, meldung = seite.rendere(beispiel(), self.vorlage, self.ziel)
        self.assertFalse(ok)
        self.assertIn("Platzhalter", meldung)


class TestExcel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pfad = Path(self.tmp.name) / "ausgabe" / "kurse.xlsx"
        self.d = beispiel()
        excel.schreibe(self.d, self.pfad)
        self.wb = openpyxl.load_workbook(self.pfad)

    def tearDown(self):
        self.tmp.cleanup()

    def test_blaetter(self):
        self.assertEqual(self.wb.sheetnames, ["Tageskurse", "Wochenschnitte", "Erklärungen", "Info"])

    def test_tageskurse_kopf_filter_datum_und_zahlenformat(self):
        ws = self.wb["Tageskurse"]
        self.assertEqual(ws.freeze_panes, "A2")
        self.assertIsNotNone(ws.auto_filter.ref)
        kopf = [c.value for c in ws[1]]
        self.assertEqual(kopf[:5], ["Datum", "Zertifikat Geld", "Zertifikat Brief", "Basiswert", "DAX"])
        self.assertEqual(ws.max_row, len(self.d["tage"]) + 1)
        zelle = ws.cell(2, 1)
        self.assertIsInstance(zelle.value, datetime)
        self.assertEqual(zelle.number_format, "DD.MM.YYYY")
        self.assertIn("0.00", ws.cell(2, 2).number_format)

    def test_diagramme(self):
        self.assertEqual(len(self.wb["Tageskurse"]._charts), 1)
        self.assertEqual(len(self.wb["Wochenschnitte"]._charts), 1)

    def test_wochen_und_erklaerungen(self):
        w = self.wb["Wochenschnitte"]
        self.assertEqual(w.cell(2, 1).value, self.d["wochen"][0]["woche"])
        e = self.wb["Erklärungen"]
        letzte = [r for r in e.iter_rows(min_row=2, values_only=True) if r[0] is not None][-1]
        self.assertIn("Das Zertifikat", letzte[1])
        self.assertIn("SAP hebt Prognose an", letzte[3])

    def test_wochen_mit_schlusskursen(self):
        ws = self.wb["Wochenschnitte"]
        kopf = [c.value for c in ws[1]]
        for k in ("Zertifikat Schluss", "Zertifikat Woche", "Basiswert Schluss", "Basiswert Woche", "DAX Schluss", "DAX Woche"):
            self.assertIn(k, kopf)
        w = self.d["wochen"][0]
        self.assertEqual(ws.cell(2, kopf.index("Zertifikat Schluss") + 1).value, w["z_schluss"])
        self.assertEqual(ws.cell(2, kopf.index("DAX Schluss") + 1).value, w["dax_schluss"])

    def test_kurssprung_spalte(self):
        d = beispiel()
        d["tage"][-1]["spruenge"] = [{"wert": "SAP", "pct": -6.1, "schwelle": 5.0}]
        with tempfile.TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "k.xlsx"
            excel.schreibe(d, pfad)
            wb = openpyxl.load_workbook(pfad)
            ws = wb["Tageskurse"]
            kopf = [c.value for c in ws[1]]
            sp = kopf.index("Kurssprung") + 1
            self.assertEqual(ws.cell(len(d["tage"]) + 1, sp).value, "SAP −6,1 %")
            self.assertIn(ws.cell(2, sp).value, (None, ""))
            wb.close()

    def test_info_blatt(self):
        werte = {r[0]: r[1] for r in self.wb["Info"].iter_rows(values_only=True) if r[0]}
        self.assertEqual(werte["ISIN"], "DE000JE3NTM6")
        self.assertIn("onvista", werte["Quelle"])
        self.assertIn("2026-11-12", werte["Abrufzeit"])

    def test_leere_daten_erzeugen_trotzdem_lesbare_datei(self):
        leer = daten.baue_daten(CONFIG, {}, {}, {}, JETZT, False, "x")
        p = Path(self.tmp.name) / "leer.xlsx"
        excel.schreibe(leer, p)
        self.assertEqual(openpyxl.load_workbook(p).sheetnames[0], "Tageskurse")


if __name__ == "__main__":
    unittest.main()
