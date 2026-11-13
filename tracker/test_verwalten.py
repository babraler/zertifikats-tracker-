"""Tests für verwalten.py (Zertifikat per Issue-Titel hinzufügen oder entfernen, Netz gemockt)."""
import contextlib
import io
import json
import tempfile
import unittest
import unittest.mock
from datetime import datetime
from pathlib import Path

import verwalten
from tracker.test_lauf import BERLIN, CONFIG, DATEN, Router

ZWEITE = "DE000VU1ABC0"  # gültige Prüfziffer
JETZT = datetime(2026, 11, 13, 19, 5, tzinfo=BERLIN)


class SnapRouter(Router):
    """Wie Router, aber der Zertifikats-Snapshot lässt sich verändern."""

    def __init__(self, typ="DISCOUNT_CERTIFICATE", **kw):
        super().__init__(**kw)
        snap = json.loads((DATEN / "zertifikat_snapshot.json").read_text(encoding="utf-8"))
        snap["derivativesDetails"]["derivativesSubCategory"]["entitySubType"] = typ
        self.snap = json.dumps(snap).encode("utf-8")

    def antwort(self, url):
        if "/derivatives/" in url and not any(t in url for t in self.fehler):
            return self.snap
        return super().antwort(url)


class Basis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = Path(self.tmp.name)
        self.schreibe_config({"repo": "a/b", "zertifikate": [{"isin": ZWEITE, "start": "2026-11-10", "wochen": 10}]})
        self.antwort = self.w / "antwort.md"

    def tearDown(self):
        self.tmp.cleanup()

    def schreibe_config(self, c):
        (self.w / "config.json").write_text(json.dumps(c), encoding="utf-8")

    def config(self):
        return json.loads((self.w / "config.json").read_text(encoding="utf-8"))

    def isins(self):
        return [z["isin"] for z in self.config()["zertifikate"]]

    def verwalte(self, titel, router=None):
        self.router = router or SnapRouter()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = verwalten.main(titel=titel, antwort=self.antwort, jetzt=JETZT, oeffnen=self.router,
                                  schlafen=lambda s: None, wurzel=self.w)
        self.out = out.getvalue()
        return code

    def text(self):
        return self.antwort.read_text(encoding="utf-8")


class TestHinzufuegen(Basis):
    def test_per_wkn(self):
        self.assertEqual(self.verwalte("Zertifikat hinzufügen: JE3NTM"), 0, self.out)
        self.assertEqual(self.isins(), [ZWEITE, "DE000JE3NTM6"])
        neu = self.config()["zertifikate"][1]
        self.assertEqual((neu["start"], neu["wochen"], neu["demo"]), ("2026-11-13", 10, False))
        self.assertEqual(self.config()["repo"], "a/b")
        self.assertIn("/derivatives/WKN:JE3NTM/snapshot", self.router.urls[0])
        self.assertTrue((self.w / "daten" / "DE000JE3NTM6" / "kurse.csv").exists())
        g = json.loads((self.w / "ausgabe" / "daten.json").read_text(encoding="utf-8"))
        self.assertEqual([z["produkt"]["isin"] for z in g["zertifikate"]], [ZWEITE, "DE000JE3NTM6"])
        self.assertIn("DE000JE3NTM6", self.text())
        self.assertIn("aufgenommen", self.text())

    def test_per_isin_und_leerzeichen_am_rand(self):
        self.assertEqual(self.verwalte("  Zertifikat hinzufügen: DE000JE3NTM6 "), 0, self.out)
        self.assertIn("/derivatives/ISIN:DE000JE3NTM6/snapshot", self.router.urls[0])

    def test_schon_verfolgt(self):
        self.schreibe_config({"zertifikate": [CONFIG]})
        self.assertEqual(self.verwalte("Zertifikat hinzufügen: JE3NTM"), 1)
        self.assertEqual(self.isins(), ["DE000JE3NTM6"])
        self.assertIn("schon", self.text())

    def test_kein_discount(self):
        self.assertEqual(self.verwalte("Zertifikat hinzufügen: JE3NTM", SnapRouter(typ="BONUS_CERTIFICATE")), 1)
        self.assertEqual(self.isins(), [ZWEITE])
        self.assertIn("Discount", self.text())

    def test_onvista_sperrt(self):
        self.assertEqual(self.verwalte("Zertifikat hinzufügen: JE3NTM", SnapRouter(fehler={"/derivatives/": 429})), 1)
        self.assertEqual(self.isins(), [ZWEITE])
        self.assertIn("429", self.text())

    def test_voll(self):
        voll = [{"isin": f"DE00{i:07d}0", "start": "2026-11-10", "wochen": 10} for i in range(10)]
        self.schreibe_config({"zertifikate": voll})
        self.assertEqual(self.verwalte("Zertifikat hinzufügen: JE3NTM"), 1)
        self.assertIn("10", self.text())


class TestEntfernen(Basis):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.verwalte("Zertifikat hinzufügen: JE3NTM"), 0)

    def test_per_wkn_aus_den_gespeicherten_stammdaten(self):
        self.assertEqual(self.verwalte("Zertifikat entfernen: JE3NTM"), 0, self.out)
        self.assertEqual(self.isins(), [ZWEITE])
        self.assertTrue((self.w / "daten" / "DE000JE3NTM6" / "kurse.csv").exists())  # Daten bleiben
        g = json.loads((self.w / "ausgabe" / "daten.json").read_text(encoding="utf-8"))
        self.assertEqual([z["produkt"]["isin"] for z in g["zertifikate"]], [ZWEITE])
        self.assertEqual(self.router.urls, [])  # ohne Netz
        self.assertIn("entfernt", self.text())

    def test_per_isin_und_das_letzte_bleibt(self):
        self.assertEqual(self.verwalte(f"Zertifikat entfernen: {ZWEITE}"), 0, self.out)
        self.assertEqual(self.verwalte("Zertifikat entfernen: DE000JE3NTM6"), 1)
        self.assertEqual(self.isins(), ["DE000JE3NTM6"])
        self.assertIn("letzte", self.text())

    def test_entfernen_und_wieder_aufnehmen(self):
        self.assertEqual(self.verwalte("Zertifikat entfernen: JE3NTM"), 0)
        self.assertEqual(self.verwalte("Zertifikat hinzufügen: JE3NTM"), 0, self.out)
        self.assertEqual(self.isins(), [ZWEITE, "DE000JE3NTM6"])
        self.assertIn("weiterverwendet", self.text())

    def test_unbekannt(self):
        self.assertEqual(self.verwalte("Zertifikat entfernen: ZZZ999"), 1)
        self.assertEqual(len(self.isins()), 2)


class TestTitel(Basis):
    def test_ungueltige_titel(self):
        for titel in ("Hallo", "Zertifikat hinzufügen: ../../etc", "Zertifikat hinzufügen: je3ntm",
                      "Zertifikat löschen: JE3NTM", "Zertifikat hinzufügen: DE000JE3NTM7",  # Prüfziffer falsch
                      "Zertifikat hinzufügen: JE3NTM; rm -rf /", "", None):
            with self.subTest(titel=titel):
                self.assertEqual(self.verwalte(titel), 2)
                self.assertEqual(self.router.urls, [])
                self.assertIn("nicht erkannt", self.text())
        self.assertEqual(self.isins(), [ZWEITE])

    def test_titel_aus_umgebung(self):
        with unittest.mock.patch.dict("os.environ", {"ISSUE_TITLE": "Zertifikat hinzufügen: JE3NTM"}):
            self.assertEqual(self.verwalte(None), 0, self.out)


if __name__ == "__main__":
    unittest.main()
