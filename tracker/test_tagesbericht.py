"""Tests für tracker/tagesbericht.py (Zusammenfassung je Handelstag, Speichern, Markdown)."""
import json
import tempfile
import unittest
from pathlib import Path

from tracker import tagesbericht as tb

TAG = {"datum": "2026-11-20", "phase": "lauf", "z_geld": 145.29, "basis": 184.64, "dax": 25001.29,
       "z_pct": -0.23, "basis_pct": -2.3, "dax_pct": -1.8, "dz": -0.34, "aktie_spez_pct": -0.5,
       "haupttreiber": "DAX-Bewegung", "verdikt": "Marktbewegung", "auffaellig": False,
       "spruenge": [{"wert": "DAX", "pct": -3.1, "schwelle": 3.0}]}
ROH = [
    {"titel": "DAX fällt unter 25.000 Punkte", "quelle": "Finanzen.net", "zeit": "2026-11-20T13:20:00+01:00",
     "url": "https://news.google.com/a"},
    {"titel": "SAP verliert nach Analystenabstufung", "quelle": "Handelsblatt", "zeit": "2026-11-20T10:00:00+01:00",
     "url": "https://news.google.com/b"},
    {"titel": "Wetter in Walldorf", "quelle": "X", "zeit": "2026-11-20T09:00:00+01:00", "url": None},
    {"titel": "EZB senkt Zins", "quelle": "Reuters", "zeit": "2026-11-20T14:00:00+01:00", "url": "https://n/c"},
]


class TestErstelle(unittest.TestCase):
    def setUp(self):
        self.b = tb.erstelle(TAG, ROH, "SAP")

    def test_gruppen_nach_name_im_titel(self):
        self.assertEqual([n["titel"] for n in self.b["nachrichten_unternehmen"]], ["SAP verliert nach Analystenabstufung"])
        self.assertEqual(len(self.b["nachrichten_markt"]), 3)
        self.assertEqual(self.b["nachrichten_gesamt"], 4)

    def test_einordnung_markt_gegen_dax_unternehmen_gegen_aktie(self):
        sap = self.b["nachrichten_unternehmen"][0]
        self.assertEqual((sap["kategorie"], sap["richtung"], sap["passt"]), ("Analyst/Kursziel", "negativ", True))
        dax = next(n for n in self.b["nachrichten_markt"] if n["titel"].startswith("DAX"))
        self.assertEqual((dax["richtung"], dax["passt"]), ("negativ", True))

    def test_wichtige_markt_news_vor_unwichtigen(self):
        self.assertEqual(self.b["nachrichten_markt"][-1]["titel"], "Wetter in Walldorf")

    def test_zusammenfassung_enthaelt_kurse_einordnung_und_news(self):
        t = self.b["zusammenfassung"]
        self.assertTrue(t.startswith("Zertifikat −0,23 %"), t)
        for teil in ("Zertifikat −0,23 % (−0,34 €)", "SAP-Aktie −2,30 %", "DAX −1,80 %", "Einordnung: Marktbewegung",
                     "Kurssprung: DAX −3,10 %", "Zu SAP: „SAP verliert nach Analystenabstufung“", "Gesamtmarkt: „EZB senkt Zins“"):
            self.assertIn(teil, t)
        self.assertEqual(self.b["hinweis"], "Zeitlicher Zusammenhang, kein Beweis.")

    def test_ohne_abruf_und_ohne_treffer(self):
        self.assertIn("keine Schlagzeilen abgerufen", tb.erstelle(TAG, None, "SAP")["zusammenfassung"])
        t = tb.erstelle(TAG, [], "SAP")["zusammenfassung"]
        self.assertIn("Zu SAP gab es keine Schlagzeile", t)
        self.assertIn("Zum Gesamtmarkt gab es keine Schlagzeile", t)

    def test_ohne_vortag(self):
        t = dict(TAG, dz=None, z_pct=None, haupttreiber=None, verdikt=None, spruenge=[])
        self.assertIn("nicht vergleichen", tb.erstelle(t, [], None)["zusammenfassung"])

    def test_berichte_nur_lauf_oder_mit_news(self):
        tage = [dict(TAG, datum="2026-11-02", phase="vorlauf"), dict(TAG, datum="2026-11-03", phase="vorlauf"), TAG]
        self.assertEqual(sorted(tb.berichte(tage, {"2026-11-03": []}, "SAP")), ["2026-11-03", "2026-11-20"])


class TestSpeichern(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.o = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_zusammenfuehren_nichts_geht_verloren(self):
        alt = tb.erstelle(dict(TAG, datum="2026-11-19"), ROH, "SAP")
        self.assertTrue(tb.speichere(self.o, {"2026-11-19": alt}, "Z", "SAP"))
        tb.speichere(self.o, {"2026-11-20": tb.erstelle(TAG, ROH, "SAP")}, "Z", "SAP")
        alle = json.loads((self.o / "tagesberichte.json").read_text(encoding="utf-8"))
        self.assertEqual(list(alle), ["2026-11-19", "2026-11-20"])
        self.assertFalse(tb.speichere(self.o, {"2026-11-20": tb.erstelle(TAG, ROH, "SAP")}, "Z", "SAP"))

    def test_kaputte_datei_wird_ersetzt(self):
        (self.o / "tagesberichte.json").write_text("{kaputt", encoding="utf-8")
        tb.speichere(self.o, {"2026-11-20": tb.erstelle(TAG, ROH, "SAP")}, "Z", "SAP")
        self.assertEqual(list(tb.lies(self.o / "tagesberichte.json")), ["2026-11-20"])

    def test_markdown_neueste_zuerst_und_maskiert(self):
        roh = [{"titel": "SAP <script>[x](javascript:y)", "quelle": "Q", "zeit": "2026-11-20T10:00:00+01:00",
                "url": "javascript:alert(1)"}]
        tb.speichere(self.o, {"2026-11-19": tb.erstelle(dict(TAG, datum="2026-11-19"), ROH, "SAP"),
                              "2026-11-20": tb.erstelle(TAG, roh, "SAP")}, "Zert [1]", "SAP")
        md = (self.o / "tagesberichte.md").read_text(encoding="utf-8")
        self.assertLess(md.index("Freitag, 20.11.2026"), md.index("Donnerstag, 19.11.2026"))
        self.assertIn("# Tagesberichte: Zert \\[1\\]", md)
        self.assertNotIn("<script>", md)
        self.assertIn("\\[x\\](javascript:y)", md)       # kein Link, weil die Klammern maskiert sind
        self.assertIn("- SAP \\<script\\>", md)            # keine https-Adresse → kein Link
        self.assertIn("[DAX fällt unter 25.000 Punkte](https://news.google.com/a) (Finanzen.net, 20.11. 13:20", md)

    def test_gegenlaeufiges_rutscht_nach_hinten(self):
        roh = [{"titel": "SAP steigt kräftig", "quelle": "A", "zeit": "2026-11-20T12:00:00+01:00", "url": None},
               {"titel": "SAP Quartal", "quelle": "B", "zeit": "2026-11-20T11:00:00+01:00", "url": None}]
        self.assertEqual(tb.erstelle(TAG, roh, "SAP")["nachrichten_unternehmen"][0]["titel"], "SAP Quartal")


if __name__ == "__main__":
    unittest.main()
