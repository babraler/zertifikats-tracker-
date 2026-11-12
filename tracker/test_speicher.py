"""Tests für tracker/speicher.py (Dateien in temporären Ordnern)."""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tracker import speicher


def zeile(datum, **kw):
    z = {c: None for c in speicher.SPALTEN}
    z["datum"] = datum
    z.update(kw)
    return z


class TestCsv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pfad = Path(self.tmp.name) / "isin" / "kurse.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def test_lesen_ohne_datei_ist_leer(self):
        self.assertEqual(speicher.lies_kurse(self.pfad), {})

    def test_schreiben_und_lesen_rundlauf_mit_leeren_feldern(self):
        rows = {"2026-11-09": zeile("2026-11-09", z_geld=140.17, z_quelle="historie", basis=211.65)}
        speicher.schreibe_kurse(self.pfad, rows)
        text = self.pfad.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("datum,z_geld,z_brief,z_quelle,basis,dax,delta,theta_tag,iv"))
        self.assertIn("2026-11-09,140.17,,historie,211.65,,,,", text)
        self.assertEqual(speicher.lies_kurse(self.pfad), rows)

    def test_sortiert_nach_datum(self):
        rows = {d: zeile(d, z_geld=1.0) for d in ("2026-11-10", "2026-11-06")}
        speicher.schreibe_kurse(self.pfad, rows)
        zeilen = self.pfad.read_text(encoding="utf-8").splitlines()
        self.assertTrue(zeilen[1].startswith("2026-11-06"))

    def test_schreiben_aendert_unveraenderte_datei_nicht(self):
        rows = {"2026-11-09": zeile("2026-11-09", z_geld=1.5)}
        self.assertTrue(speicher.schreibe_kurse(self.pfad, rows))
        self.assertFalse(speicher.schreibe_kurse(self.pfad, rows))

    def test_kaputte_zahl_wird_leer(self):
        self.pfad.parent.mkdir(parents=True)
        self.pfad.write_text("datum,z_geld,z_brief,z_quelle,basis,dax,delta,theta_tag,iv\n2026-11-09,abc,,,,,,,\nkein-datum,1,,,,,,,\n", encoding="utf-8")
        rows = speicher.lies_kurse(self.pfad)
        self.assertEqual(list(rows), ["2026-11-09"])
        self.assertIsNone(rows["2026-11-09"]["z_geld"])


class TestZusammenfuehren(unittest.TestCase):
    def test_historie_fuellt_nur_leeres(self):
        rows = {"2026-11-06": zeile("2026-11-06", z_geld=140.2, z_quelle="snapshot")}
        neu = speicher.fuelle_historie(rows, {"z": {"2026-11-06": 140.0, "2026-11-05": 139.9},
                                              "basis": {"2026-11-06": 210.75}, "dax": {"2026-11-06": 25820.36}})
        self.assertEqual(neu["2026-11-06"]["z_geld"], 140.2)
        self.assertEqual(neu["2026-11-06"]["z_quelle"], "snapshot")
        self.assertEqual(neu["2026-11-06"]["basis"], 210.75)
        self.assertEqual(neu["2026-11-05"]["z_geld"], 139.9)
        self.assertEqual(neu["2026-11-05"]["z_quelle"], "historie")

    def test_eingabe_bleibt_unveraendert(self):
        rows = {"2026-11-06": zeile("2026-11-06")}
        speicher.fuelle_historie(rows, {"z": {"2026-11-06": 1.0}, "basis": {}, "dax": {}})
        self.assertIsNone(rows["2026-11-06"]["z_geld"])

    def test_historie_ohne_zertifikatskurs_laesst_quelle_leer(self):
        neu = speicher.fuelle_historie({}, {"z": {}, "basis": {"2026-11-09": 211.65}, "dax": {}})
        self.assertIsNone(neu["2026-11-09"]["z_quelle"])

    def test_snapshot_ueberschreibt_nichts(self):
        rows = {"2026-11-09": zeile("2026-11-09", basis=211.65)}
        neu = speicher.fuelle_snapshot(rows, "2026-11-09", {"z_geld": 140.18, "z_brief": 140.68, "basis": 212.75,
                                                            "dax": 26267.19, "delta": 0.07, "theta_tag": 0.03, "iv": 47.6})
        z = neu["2026-11-09"]
        self.assertEqual((z["basis"], z["z_geld"], z["z_quelle"]), (211.65, 140.18, "snapshot"))

    def test_snapshot_mit_none_legt_zeile_trotzdem_an(self):
        neu = speicher.fuelle_snapshot({}, "2026-11-09", {"z_geld": None, "basis": None})
        self.assertIn("2026-11-09", neu)
        self.assertIsNone(neu["2026-11-09"]["z_quelle"])

    def test_vollstaendig(self):
        voll = zeile("d", z_geld=1.0, z_brief=1.1, basis=2.0, dax=3.0, z_quelle="snapshot")
        self.assertTrue(speicher.ist_vollstaendig(voll))
        self.assertFalse(speicher.ist_vollstaendig(dict(voll, dax=None)))
        self.assertFalse(speicher.ist_vollstaendig(None))


class TestWochen(unittest.TestCase):
    def rows(self):
        werte = {  # KW46: 10.-13.11. (4 Tage), KW47: 16.-20.11. (5 Tage)
            "2026-11-06": (100.0, 200.0, 10000.0),
            "2026-11-10": (110.0, 210.0, 10100.0), "2026-11-11": (112.0, 212.0, 10200.0),
            "2026-11-12": (111.0, 211.0, 10300.0), "2026-11-13": (115.0, 215.0, 10400.0),
            "2026-11-16": (120.0, 220.0, 10500.0), "2026-11-17": (121.0, 221.0, 10600.0),
            "2026-11-18": (122.0, 222.0, 10700.0), "2026-11-19": (123.0, 223.0, 10800.0),
            "2026-11-20": (124.0, 224.0, 10900.0),
        }
        return {d: zeile(d, z_geld=z, basis=b, dax=x) for d, (z, b, x) in werte.items()}

    def test_schnitte_von_hand(self):
        w = speicher.wochenschnitte(self.rows(), date(2026, 11, 10))
        self.assertEqual([x["woche"] for x in w], ["2026-W46", "2026-W47"])
        w46 = w[0]
        self.assertAlmostEqual(w46["z_schnitt"], (110 + 112 + 111 + 115) / 4)
        self.assertAlmostEqual(w46["basis_schnitt"], (210 + 212 + 211 + 215) / 4)
        self.assertAlmostEqual(w46["dax_schnitt"], (10100 + 10200 + 10300 + 10400) / 4)
        self.assertEqual((w46["tage"], w46["von"], w46["bis"]), (4, "2026-11-10", "2026-11-13"))
        self.assertTrue(w46["unvollstaendig"])
        self.assertIsNone(w46["z_vorwoche_pct"])

    def test_aenderung_zur_vorwoche(self):
        w = speicher.wochenschnitte(self.rows(), date(2026, 11, 10))
        s46, s47 = (110 + 112 + 111 + 115) / 4, 122.0
        self.assertAlmostEqual(w[1]["z_schnitt"], s47)
        self.assertAlmostEqual(w[1]["z_vorwoche_pct"], (s47 / s46 - 1) * 100)
        self.assertFalse(w[1]["unvollstaendig"])

    def test_zeilen_vor_start_zaehlen_nicht(self):
        w = speicher.wochenschnitte(self.rows(), date(2026, 11, 12))
        self.assertEqual(w[0]["von"], "2026-11-12")
        self.assertEqual(w[0]["tage"], 2)

    def test_leer(self):
        self.assertEqual(speicher.wochenschnitte({}, date(2026, 11, 10)), [])


class TestJsonDateien(unittest.TestCase):
    def test_meta_und_nachrichten(self):
        with tempfile.TemporaryDirectory() as t:
            ordner = Path(t) / "x"
            self.assertEqual(speicher.lies_meta(ordner / "meta.json"), {})
            speicher.schreibe_meta(ordner / "meta.json", {"name": "Größe"})
            self.assertEqual(speicher.lies_meta(ordner / "meta.json"), {"name": "Größe"})
            p = ordner / "nachrichten.jsonl"
            self.assertEqual(speicher.lies_nachrichten(p), {})
            speicher.haenge_nachrichten_an(p, "2026-11-09", [{"titel": "A", "url": "https://a"}])
            speicher.haenge_nachrichten_an(p, "2026-11-08", [])
            n = speicher.lies_nachrichten(p)
            self.assertEqual(n["2026-11-09"][0]["titel"], "A")
            self.assertEqual(n["2026-11-08"], [])

    def test_kaputte_zeile_in_nachrichten_wird_uebersprungen(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "n.jsonl"
            p.write_text('{"datum": "2026-11-09", "titel": "A"}\nkaputt\n', encoding="utf-8")
            self.assertEqual(list(speicher.lies_nachrichten(p)), ["2026-11-09"])


if __name__ == "__main__":
    unittest.main()
