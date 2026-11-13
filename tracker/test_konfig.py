"""Tests für tracker/konfig.py (config.json mit einem oder mehreren Zertifikaten)."""
import json
import tempfile
import unittest
from pathlib import Path

from tracker import konfig

EINS = {"isin": "DE000JE3NTM6", "demo": True, "start": "2026-11-10", "wochen": 10, "basis_suchbegriff": None}
ZWEI = {"isin": "DE000VU1ABC2", "start": "2026-11-13", "wochen": 10}


class Basis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pfad = Path(self.tmp.name) / "config.json"

    def tearDown(self):
        self.tmp.cleanup()

    def lade(self, obj):
        self.pfad.write_text(json.dumps(obj), encoding="utf-8")
        return konfig.lade_config(self.pfad)


class TestFormate(Basis):
    def test_altes_einzelformat_wird_liste(self):
        c = self.lade({**EINS, "sprung_pct": {"basis": 4}})
        self.assertEqual([z["isin"] for z in c["zertifikate"]], ["DE000JE3NTM6"])
        z = c["zertifikate"][0]
        self.assertEqual((z["start"], z["wochen"], z["demo"], z["basis_suchbegriff"]), ("2026-11-10", 10, True, None))
        self.assertEqual(z["sprung_pct"], {"basis": 4.0})

    def test_neues_listenformat_mit_globalen_und_eigenen_schwellen(self):
        c = self.lade({"sprung_pct": {"z": 3}, "zertifikate": [EINS, {**ZWEI, "sprung_pct": {"z": 1.5}}]})
        self.assertEqual([z["isin"] for z in c["zertifikate"]], ["DE000JE3NTM6", "DE000VU1ABC2"])
        self.assertEqual(c["zertifikate"][0]["sprung_pct"], {"z": 3.0})
        self.assertEqual(c["zertifikate"][1]["sprung_pct"], {"z": 1.5})
        self.assertFalse(c["zertifikate"][1]["demo"])

    def test_schreiben_und_wieder_lesen(self):
        c = self.lade({"zertifikate": [EINS]})
        c2 = konfig.mit_zertifikat(c, "DE000VU1ABC2", "2026-11-13")
        konfig.schreibe_config(self.pfad, c2)
        neu = konfig.lade_config(self.pfad)
        self.assertEqual([z["isin"] for z in neu["zertifikate"]], ["DE000JE3NTM6", "DE000VU1ABC2"])
        self.assertEqual(neu["zertifikate"][1]["wochen"], konfig.STANDARD_WOCHEN)
        self.assertEqual(len(c["zertifikate"]), 1)  # Eingabe bleibt unverändert

    def test_repo_optional_und_geprueft(self):
        self.assertIsNone(self.lade({"zertifikate": [EINS]})["repo"])
        c = self.lade({"repo": "babraler/zertifikats-tracker-", "zertifikate": [EINS]})
        self.assertEqual(c["repo"], "babraler/zertifikats-tracker-")
        konfig.schreibe_config(self.pfad, konfig.mit_zertifikat(c, "DE000VU1ABC2", "2026-11-13"))
        self.assertEqual(konfig.lade_config(self.pfad)["repo"], "babraler/zertifikats-tracker-")
        for kaputt in ("../x", "a/b/c", "a b/c", 5):
            with self.subTest(kaputt=kaputt), self.assertRaises(konfig.ConfigFehler):
                self.lade({"repo": kaputt, "zertifikate": [EINS]})


class TestFehler(Basis):
    def pruefe(self, obj):
        with self.assertRaises(konfig.ConfigFehler):
            self.lade(obj)

    def test_ungueltige_eintraege(self):
        for kaputt in ({**EINS, "isin": "../../x"}, {**EINS, "start": "morgen"}, {**EINS, "wochen": 0}, {"isin": "x"},
                       {**EINS, "sprung_pct": {"z": -1}}, {**EINS, "sprung_pct": {"aktie": 5}}, {**EINS, "sprung_pct": "5"},
                       {"zertifikate": []}, {"zertifikate": "x"}, {"zertifikate": [EINS, EINS]}):
            with self.subTest(kaputt=kaputt):
                self.pruefe(kaputt)

    def test_hoechstens_zehn(self):
        liste = [{**ZWEI, "isin": f"DE00{i:07d}0"} for i in range(11)]
        self.pruefe({"zertifikate": liste})

    def test_datei_fehlt(self):
        with self.assertRaises(konfig.ConfigFehler):
            konfig.lade_config(self.pfad)


class TestAendern(Basis):
    def test_hinzufuegen_doppelt_und_voll(self):
        c = self.lade({"zertifikate": [EINS]})
        with self.assertRaises(konfig.ConfigFehler):
            konfig.mit_zertifikat(c, "DE000JE3NTM6", "2026-11-13")
        with self.assertRaises(konfig.ConfigFehler):
            konfig.mit_zertifikat(c, "KEINEISIN", "2026-11-13")
        voll = {"zertifikate": [{**ZWEI, "isin": f"DE00{i:07d}0"} for i in range(10)]}
        with self.assertRaises(konfig.ConfigFehler):
            konfig.mit_zertifikat(self.lade(voll), "DE000JE3NTM6", "2026-11-13")

    def test_hinzufuegen_haengt_hinten_an(self):
        c = konfig.mit_zertifikat(self.lade({"zertifikate": [EINS]}), "DE000VU1ABC2", "2026-11-13")
        self.assertEqual([z["isin"] for z in c["zertifikate"]], ["DE000JE3NTM6", "DE000VU1ABC2"])

    def test_entfernen(self):
        c = self.lade({"zertifikate": [EINS, ZWEI]})
        self.assertEqual([z["isin"] for z in konfig.ohne_zertifikat(c, "DE000JE3NTM6")["zertifikate"]], ["DE000VU1ABC2"])
        with self.assertRaises(konfig.ConfigFehler):
            konfig.ohne_zertifikat(c, "DE0000000000")  # nicht vorhanden
        with self.assertRaises(konfig.ConfigFehler):  # das letzte bleibt
            konfig.ohne_zertifikat(self.lade({"zertifikate": [EINS]}), "DE000JE3NTM6")


if __name__ == "__main__":
    unittest.main()
