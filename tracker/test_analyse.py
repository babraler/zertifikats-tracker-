"""Tests für tracker/analyse.py (reine Funktionen, von Hand nachgerechnete Werte)."""
import math
import random
import unittest
from datetime import date, timedelta

from tracker import analyse


def zeile(datum, z, s, dax, delta=None, theta=None):
    return {"datum": datum, "z_geld": z, "z_brief": None if z is None else z + 0.5, "z_quelle": "snapshot",
            "basis": s, "dax": dax, "delta": delta, "theta_tag": theta, "iv": None}


def reihe(n, start=date(2026, 9, 1), beta=1.5, rausch=0.0, seed=1, delta=0.5, theta=0.0, z0=100.0):
    """n Werktage; Basiswertrendite = beta * DAX-Rendite + Rauschen."""
    rnd = random.Random(seed)
    rows, s, dax, z, d = [], 200.0, 10000.0, z0, start
    for i in range(n):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        rows.append(zeile(d.isoformat(), z, s, dax, delta, theta))
        r = rnd.uniform(-0.01, 0.01)
        e = rnd.uniform(-rausch, rausch) if rausch else 0.0
        dax *= 1 + r
        s *= 1 + beta * r + e
        z += delta * 0.1
        d += timedelta(days=1)
    return rows


class TestBeta(unittest.TestCase):
    def test_beta_aus_regression(self):
        rows = reihe(40, beta=1.5)
        a = analyse.analysiere(rows)
        self.assertAlmostEqual(a[35]["beta"], 1.5, places=6)
        self.assertFalse(a[35]["beta_geschaetzt"])

    def test_zu_wenig_punkte_gibt_eins_und_geschaetzt(self):
        a = analyse.analysiere(reihe(10, beta=1.5))
        self.assertEqual(a[8]["beta"], 1.0)
        self.assertTrue(a[8]["beta_geschaetzt"])

    def test_fenster_hoechstens_60_tage_vor_t(self):
        reiche = reihe(100, beta=1.5)
        # ab Tag 40 anderes Beta; Fenster für Tag 99 deckt nur noch Tage 39..98 ab
        for i in range(39, 100):
            r_dax = reiche[i]["dax"] / reiche[i - 1]["dax"] - 1
            reiche[i]["basis"] = reiche[i - 1]["basis"] * (1 + 0.5 * r_dax)
        a = analyse.analysiere(reiche)
        self.assertAlmostEqual(a[99]["beta"], 0.5, places=6)

    def test_nullvarianz_dax_gibt_eins(self):
        rows = [zeile(f"2026-10-{i:02d}", 100.0, 200.0 + i, 10000.0) for i in range(1, 29) if date(2026, 10, i).weekday() < 5]
        a = analyse.analysiere(rows)
        self.assertEqual(a[-1]["beta"], 1.0)
        self.assertTrue(a[-1]["beta_geschaetzt"])


class TestEffekte(unittest.TestCase):
    def setUp(self):
        # Montag 2026-11-09 → Dienstag: genau 1 Kalendertag. Von Hand: siehe Kommentare.
        self.rows = [zeile("2026-11-09", 100.0, 200.0, 10000.0),
                     zeile("2026-11-10", 100.5, 204.0, 10100.0, delta=0.5, theta=0.02)]
        self.t = analyse.analysiere(self.rows, bezug=1.0, cap=150.0, basis_name="SAP")[1]

    def test_renditen_und_dz(self):
        self.assertAlmostEqual(self.t["z_pct"], 0.5)
        self.assertAlmostEqual(self.t["basis_pct"], 2.0)
        self.assertAlmostEqual(self.t["dax_pct"], 1.0)
        self.assertAlmostEqual(self.t["dz"], 0.5)

    def test_effekte_von_hand(self):
        self.assertAlmostEqual(self.t["effekt_basis"], 0.5 * 1.0 * 4.0)         # 2,00
        self.assertAlmostEqual(self.t["effekt_markt"], 0.5 * 200.0 * 1.0 * 0.01)  # 1,00 (Beta 1,0 geschätzt)
        self.assertAlmostEqual(self.t["effekt_aktie"], 1.0)
        self.assertAlmostEqual(self.t["effekt_zeit"], 0.02)
        self.assertAlmostEqual(self.t["effekt_rest"], 0.5 - 2.0 - 0.02)

    def test_summe_stimmt(self):
        t = self.t
        self.assertAlmostEqual(t["effekt_basis"] + t["effekt_zeit"] + t["effekt_rest"], t["dz"])
        self.assertAlmostEqual(t["effekt_markt"] + t["effekt_aktie"], t["effekt_basis"])

    def test_haupttreiber_ist_betragsgroesster(self):
        self.assertEqual(self.t["haupttreiber"], "Sonstiges (Spread, Vola, Zinsen)")

    def test_wochenende_zaehlt_drei_kalendertage_zeit(self):
        rows = [zeile("2026-11-06", 100.0, 200.0, 10000.0), zeile("2026-11-09", 100.0, 200.0, 10000.0, delta=0.5, theta=0.02)]
        self.assertAlmostEqual(analyse.analysiere(rows)[1]["effekt_zeit"], 0.06)

    def test_bezug_geht_in_basiseffekt_ein(self):
        t = analyse.analysiere(self.rows, bezug=0.1)[1]
        self.assertAlmostEqual(t["effekt_basis"], 0.5 * 0.1 * 4.0)

    def test_erster_tag_und_luecken_bleiben_leer(self):
        rows = [zeile("2026-11-06", 100.0, 200.0, 10000.0), zeile("2026-11-09", None, 201.0, 10050.0),
                zeile("2026-11-10", 101.0, 202.0, 10060.0)]
        a = analyse.analysiere(rows)
        for i in (0, 1, 2):
            self.assertIsNone(a[i]["dz"], i)
            self.assertIsNone(a[i]["haupttreiber"])
            self.assertIsNone(a[i]["auffaellig"])
        self.assertIn("Vortag", a[2]["text"])


class TestDeltaTheta(unittest.TestCase):
    def test_delta_vom_tag_sonst_letzter_bekannter(self):
        rows = [zeile("2026-11-05", 100.0, 200.0, 10000.0, delta=0.2),
                zeile("2026-11-06", 100.0, 202.0, 10000.0),
                zeile("2026-11-09", 100.0, 202.0, 10000.0, delta=0.4)]
        a = analyse.analysiere(rows)
        self.assertEqual((a[1]["delta"], a[1]["delta_geschaetzt"]), (0.2, False))
        self.assertEqual(a[2]["delta"], 0.4)

    def test_delta_aus_spaeterem_tag_wenn_frueher_unbekannt(self):
        rows = [zeile("2026-11-05", 100.0, 200.0, 10000.0), zeile("2026-11-06", 100.0, 202.0, 10000.0),
                zeile("2026-11-09", 100.0, 202.0, 10000.0, delta=0.3)]
        a = analyse.analysiere(rows)
        self.assertEqual((a[1]["delta"], a[1]["delta_geschaetzt"]), (0.3, False))

    def test_delta_nirgends_bekannt_naeherung_halb(self):
        rows = [zeile("2026-11-05", 100.0, 200.0, 10000.0), zeile("2026-11-06", 100.0, 202.0, 10000.0)]
        t = analyse.analysiere(rows)[1]
        self.assertEqual((t["delta"], t["delta_geschaetzt"]), (0.5, True))
        self.assertAlmostEqual(t["effekt_basis"], 1.0)

    def test_theta_fehlt_letzter_bekannter_sonst_null(self):
        rows = [zeile("2026-11-05", 100.0, 200.0, 10000.0, theta=0.04), zeile("2026-11-06", 100.0, 202.0, 10000.0)]
        self.assertAlmostEqual(analyse.analysiere(rows)[1]["effekt_zeit"], 0.04)
        rows[0]["theta_tag"] = None
        self.assertAlmostEqual(analyse.analysiere(rows)[1]["effekt_zeit"], 0.0)


class TestAuffaellig(unittest.TestCase):
    def test_grosser_aktiensprung_ist_auffaellig(self):
        rows = reihe(45, beta=1.0, rausch=0.002)
        rows[-1]["basis"] = rows[-2]["basis"] * 1.06
        t = analyse.analysiere(rows)[-1]
        self.assertTrue(t["auffaellig"])
        self.assertGreaterEqual(t["z_score"], 1.5)

    def test_normaler_tag_nicht_auffaellig(self):
        rows = reihe(45, beta=1.0, rausch=0.002)
        a = analyse.analysiere(rows)
        self.assertFalse(a[-1]["auffaellig"] and abs(a[-1]["z_score"]) < 1.5)
        self.assertTrue(all((not t["auffaellig"]) or abs(t["z_score"]) >= 1.5 for t in a if t["z_score"] is not None))

    def test_zu_wenig_vorlauf_kein_score(self):
        t = analyse.analysiere(reihe(15, rausch=0.002))[-1]
        self.assertIsNone(t["z_score"])
        self.assertFalse(t["auffaellig"])

    def test_aktienspezifische_rendite_wird_ausgegeben(self):
        t = analyse.analysiere(reihe(45, beta=1.0, rausch=0.002))[-1]
        self.assertTrue(math.isfinite(t["aktie_spez_pct"]))


class TestCapUndText(unittest.TestCase):
    def test_cap_abstand(self):
        self.assertAlmostEqual(analyse.cap_abstand_pct(211.65, 142.5), (211.65 - 142.5) / 142.5 * 100)
        self.assertIsNone(analyse.cap_abstand_pct(None, 142.5))
        self.assertIsNone(analyse.cap_abstand_pct(100.0, None))

    def test_zahlenformat_deutsch(self):
        self.assertEqual(analyse.de(1234.5, 2), "1.234,50")
        self.assertEqual(analyse.de(-0.5, 2, vorzeichen=True), "−0,50")
        self.assertEqual(analyse.de(0.5, 2, vorzeichen=True), "+0,50")
        self.assertEqual(analyse.de(None, 2), "unbekannt")

    def test_text_nennt_zertifikat_aktie_delta_zeit_treiber(self):
        rows = [zeile("2026-11-09", 100.0, 200.0, 10000.0), zeile("2026-11-10", 100.5, 204.0, 10100.0, delta=0.5, theta=0.02)]
        t = analyse.analysiere(rows, bezug=1.0, cap=150.0, basis_name="SAP")[1]["text"]
        self.assertIn("Das Zertifikat stieg", t)
        self.assertIn("0,50 €", t)
        self.assertIn("0,50 %", t)
        self.assertIn("SAP-Aktie", t)
        self.assertIn("DAX", t)
        self.assertIn("Zeitwert", t)
        self.assertIn("Sonstiges (Spread, Vola, Zinsen)", t)
        self.assertLessEqual(t.count(". ") + 1, 4)

    def test_text_ueber_cap_mit_kleinem_delta(self):
        rows = [zeile("2026-11-09", 140.0, 200.0, 10000.0), zeile("2026-11-10", 140.1, 204.0, 10100.0, delta=0.07, theta=0.03)]
        t = analyse.analysiere(rows, cap=142.5, basis_name="SAP")[1]
        self.assertAlmostEqual(t["cap_abstand_pct"], (204 - 142.5) / 142.5 * 100)
        self.assertIn("Höchstwert", t["text"])

    def test_text_fiel_und_unveraendert(self):
        rows = [zeile("2026-11-09", 100.0, 200.0, 10000.0), zeile("2026-11-10", 99.0, 200.0, 10000.0, delta=0.5)]
        self.assertIn("fiel", analyse.analysiere(rows)[1]["text"])
        rows[1]["z_geld"] = 100.0
        self.assertIn("unverändert", analyse.analysiere(rows)[1]["text"])


if __name__ == "__main__":
    unittest.main()
