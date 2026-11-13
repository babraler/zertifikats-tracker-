"""Tests für tracker/daten.py (Zusammenbau von daten.json)."""
import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from tracker import daten

BERLIN = ZoneInfo("Europe/Berlin")
CONFIG = {"isin": "DE000JE3NTM6", "demo": True, "start": "2026-11-10", "wochen": 10, "basis_suchbegriff": None}
META = {
    "produkt": {"isin": "DE000JE3NTM6", "wkn": "JE3NTM", "name": "DISCOUNT CERTIFICATE AUF SAP SE", "emittent": "J.P. Morgan",
                "cap": 142.5, "bezug": 1.0, "faellig": "2027-03-19", "basis_name": "SAP", "basis_isin": "DE0007164600"},
    "kennzahlen": {"max_ertrag_eur": 2.33, "max_ertrag_pct": 1.66, "discount_pct": 33.65},
}
JETZT = datetime(2026, 11, 12, 18, 40, tzinfo=BERLIN)


def rows(von, bis):
    erg, d, s = {}, von, 0
    while d <= bis:
        if d.weekday() < 5:
            k = d.isoformat()
            erg[k] = {"datum": k, "z_geld": 140.0 + s * 0.1, "z_brief": 140.5 + s * 0.1, "z_quelle": "snapshot",
                      "basis": 211.0 + s, "dax": 26000.0 + 10 * s, "delta": 0.07, "theta_tag": 0.03, "iv": 47.0}
            s += 1
        d += timedelta(days=1)
    return erg


class TestBaue(unittest.TestCase):
    def setUp(self):
        self.r = rows(date(2026, 8, 12), date(2026, 11, 12))
        self.d = daten.baue_daten(CONFIG, META, self.r, {}, JETZT, ok=True, meldung="")

    def test_oberstruktur_und_produkt(self):
        self.assertEqual(list(self.d), ["stand", "produkt", "aktuell", "fortschritt", "tage", "wochen", "status"])
        self.assertEqual(self.d["stand"], "2026-11-12T18:40:00+01:00")
        p = self.d["produkt"]
        self.assertEqual((p["isin"], p["cap"], p["lauf_start"], p["lauf_ende"]), ("DE000JE3NTM6", 142.5, "2026-11-10", "2027-01-18"))
        self.assertTrue(p["demo"])

    def test_vorlauf_hoechstens_30_kalendertage(self):
        vor = [t for t in self.d["tage"] if t["phase"] == "vorlauf"]
        self.assertEqual(vor[0]["datum"], "2026-10-12")
        self.assertEqual(vor[-1]["datum"], "2026-11-09")
        self.assertEqual([t["datum"] for t in self.d["tage"] if t["phase"] == "lauf"], ["2026-11-10", "2026-11-11", "2026-11-12"])

    def test_tag_felder_nach_vertrag(self):
        t = self.d["tage"][-1]
        for k in ("datum", "phase", "z_geld", "z_brief", "z_quelle", "basis", "dax", "z_pct", "basis_pct", "dax_pct", "dz",
                  "delta", "beta", "effekt_markt", "effekt_aktie", "effekt_zeit", "effekt_rest", "haupttreiber",
                  "auffaellig", "z_score", "text", "verdikt", "nachrichten"):
            self.assertIn(k, t)
        self.assertEqual(t["nachrichten"], [])

    def test_effekte_summe_stimmt_im_ergebnis(self):
        for t in self.d["tage"]:
            if t["dz"] is not None:
                self.assertAlmostEqual(t["effekt_basis"] + t["effekt_zeit"] + t["effekt_rest"], t["dz"], places=4)

    def test_aktuell_fortschritt_wochen_status(self):
        a = self.d["aktuell"]
        self.assertEqual((a["z_geld"], a["max_ertrag_eur"], a["discount_pct"]), (self.r["2026-11-12"]["z_geld"], 2.33, 33.65))
        self.assertAlmostEqual(a["cap_abstand_pct"], (self.r["2026-11-12"]["basis"] - 142.5) / 142.5 * 100)
        self.assertEqual(self.d["fortschritt"], {"tag": 3, "tage_gesamt": 70, "woche": 1})
        self.assertEqual(self.d["wochen"][0]["woche"], "2026-W46")
        self.assertEqual(self.d["status"], {"ok": True, "meldung": "", "letzter_lauf": "2026-11-12T18:40:00+01:00"})

    def test_seit_start_bezug_ist_letzter_schluss_vor_start(self):
        s = self.d["aktuell"]["seit_start"]
        ref, jetzt = self.r["2026-11-09"], self.r["2026-11-12"]
        self.assertEqual(s["bezug_datum"], "2026-11-09")
        self.assertAlmostEqual(s["z_eur"], jetzt["z_geld"] - ref["z_geld"], places=5)
        self.assertAlmostEqual(s["z_pct"], (jetzt["z_geld"] / ref["z_geld"] - 1) * 100, places=5)
        self.assertAlmostEqual(s["basis_pct"], (jetzt["basis"] / ref["basis"] - 1) * 100, places=5)
        self.assertAlmostEqual(s["dax_pct"], (jetzt["dax"] / ref["dax"] - 1) * 100, places=5)

    def test_seit_start_ohne_vorlauf_ist_leer(self):
        r = {d: v for d, v in self.r.items() if d >= "2026-11-10"}
        s = daten.baue_daten(CONFIG, META, r, {}, JETZT, True, "")["aktuell"]["seit_start"]
        self.assertEqual(s, {"bezug_datum": None, "z_eur": None, "z_pct": None, "basis_pct": None, "dax_pct": None})

    def test_seit_start_leer_solange_kein_kurs_im_lauf(self):
        r = {d: v for d, v in self.r.items() if d < "2026-11-10"}
        s = daten.baue_daten(CONFIG, META, r, {}, JETZT, True, "")["aktuell"]["seit_start"]
        self.assertIsNone(s["z_pct"])

    def test_stand_zeit_getrennt_vom_fortschritt(self):
        abruf = datetime(2026, 11, 10, 18, 40, tzinfo=BERLIN)
        d = daten.baue_daten(CONFIG, META, self.r, {}, JETZT, True, "", stand_zeit=abruf)
        self.assertEqual((d["stand"], d["fortschritt"]["tag"]), ("2026-11-10T18:40:00+01:00", 3))

    def test_kurssprung_je_wert_eigene_schwelle(self):
        r = dict(self.r)
        r["2026-11-12"] = dict(r["2026-11-12"], basis=r["2026-11-11"]["basis"] * 1.06, dax=r["2026-11-11"]["dax"] * 1.02)
        t = daten.baue_daten(CONFIG, META, r, {}, JETZT, True, "")["tage"][-1]
        self.assertEqual([s["wert"] for s in t["spruenge"]], ["SAP"])
        self.assertAlmostEqual(t["spruenge"][0]["pct"], 6.0, places=4)
        self.assertEqual(t["spruenge"][0]["schwelle"], 5.0)

    def test_kurssprung_genau_auf_schwelle_und_nach_unten(self):
        r = dict(self.r)
        r["2026-11-12"] = dict(r["2026-11-12"], dax=r["2026-11-11"]["dax"] * 0.97)
        t = daten.baue_daten(CONFIG, META, r, {}, JETZT, True, "")["tage"][-1]
        self.assertEqual([(s["wert"], round(s["pct"], 4)) for s in t["spruenge"]], [("DAX", -3.0)])

    def test_kurssprung_schwellen_aus_config(self):
        cfg = dict(CONFIG, sprung_pct={"z": 2.0, "basis": 0.1, "dax": 3.0})
        t = daten.baue_daten(cfg, META, self.r, {}, JETZT, True, "")["tage"][-1]
        self.assertEqual([s["wert"] for s in t["spruenge"]], ["SAP"])

    def test_ohne_sprung_leere_liste_und_erster_tag_ohne_vortag(self):
        d = daten.baue_daten(CONFIG, META, self.r, {}, JETZT, True, "")
        self.assertEqual(d["tage"][-1]["spruenge"], [])
        self.assertEqual(d["produkt"]["sprung_pct"], {"z": 2.0, "basis": 5.0, "dax": 3.0})

    def test_fortschritt_vor_start_und_nach_ende(self):
        vor = daten.baue_daten(CONFIG, META, self.r, {}, datetime(2026, 11, 9, 18, 40, tzinfo=BERLIN), True, "")
        self.assertEqual(vor["fortschritt"]["tag"], 0)
        nach = daten.baue_daten(CONFIG, META, self.r, {}, datetime(2027, 3, 1, 18, 40, tzinfo=BERLIN), True, "")
        self.assertEqual(nach["fortschritt"], {"tag": 70, "tage_gesamt": 70, "woche": 10})

    def test_nachrichten_und_verdikt_werden_zugeordnet(self):
        roh = {"2026-11-12": [{"titel": "SAP hebt Prognose an", "quelle": "Q", "zeit": "2026-11-12T10:00:00+01:00", "url": "https://x"}]}
        t = daten.baue_daten(CONFIG, META, self.r, roh, JETZT, True, "")["tage"][-1]
        self.assertEqual(t["nachrichten"][0]["kategorie"], "Prognose")
        self.assertIsNotNone(t["verdikt"])

    def test_leere_daten_sind_ok(self):
        d = daten.baue_daten(CONFIG, {}, {}, {}, JETZT, False, "Fehler")
        self.assertEqual(d["tage"], [])
        self.assertIsNone(d["aktuell"]["z_geld"])
        self.assertEqual(d["status"]["ok"], False)
        self.assertEqual(d["produkt"]["isin"], "DE000JE3NTM6")

    def test_laufende(self):
        self.assertEqual(daten.lauf_ende(CONFIG), date(2027, 1, 18))


if __name__ == "__main__":
    unittest.main()
