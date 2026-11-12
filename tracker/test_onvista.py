"""Tests für tracker/onvista.py. Kein Netz: Öffnen und Warten werden ersetzt."""
import io
import json
import unittest
import urllib.error
from datetime import date
from pathlib import Path

from tracker import onvista

DATEN = Path(__file__).parent / "testdaten"


def lade(name):
    return json.loads((DATEN / name).read_text(encoding="utf-8"))


class FakeAntwort:
    def __init__(self, inhalt):
        self._b = inhalt
        self.status = 200

    def read(self, n=-1):
        return self._b if n < 0 else self._b[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def skript(*schritte):
    """Liefert einen Öffner, der die Schritte nacheinander abspielt."""
    aufrufe = []
    it = iter(schritte)

    def oeffnen(req, timeout=None):
        aufrufe.append((req.full_url, req.get_header("User-agent"), timeout))
        s = next(it)
        if isinstance(s, Exception):
            raise s
        return FakeAntwort(s)

    oeffnen.aufrufe = aufrufe
    return oeffnen


def http_fehler(code):
    return urllib.error.HTTPError("http://x", code, "x", {}, io.BytesIO(b""))


def kein_warten(sekunden):
    return None


class TestAbruf(unittest.TestCase):
    def test_ehrlicher_user_agent_und_timeout(self):
        o = skript(b'{"a": 1}')
        self.assertEqual(onvista.hole_json("https://api.onvista.de/x", oeffnen=o, schlafen=kein_warten), {"a": 1})
        _, ua, timeout = o.aufrufe[0]
        self.assertEqual(ua, "discount-tracker/1.0 (privat)")
        self.assertEqual(timeout, 20)

    def test_wiederholt_bei_5xx(self):
        o = skript(http_fehler(503), b"{}")
        onvista.hole_json("https://api.onvista.de/x", oeffnen=o, schlafen=kein_warten)
        self.assertEqual(len(o.aufrufe), 2)

    def test_gibt_nach_zwei_wiederholungen_auf(self):
        o = skript(http_fehler(500), http_fehler(502), http_fehler(503))
        with self.assertRaises(onvista.AbrufFehler):
            onvista.hole_json("https://api.onvista.de/x", oeffnen=o, schlafen=kein_warten)
        self.assertEqual(len(o.aufrufe), 3)

    def test_netzfehler_wird_wiederholt(self):
        o = skript(urllib.error.URLError("weg"), b"{}")
        onvista.hole_json("https://api.onvista.de/x", oeffnen=o, schlafen=kein_warten)
        self.assertEqual(len(o.aufrufe), 2)

    def test_sperre_bricht_sofort_ab(self):
        for code in (403, 429):
            o = skript(http_fehler(code), b"{}")
            with self.assertRaises(onvista.GesperrtFehler) as cm:
                onvista.hole_json("https://api.onvista.de/x", oeffnen=o, schlafen=kein_warten)
            self.assertEqual(len(o.aufrufe), 1)
            self.assertIn(str(code), str(cm.exception))

    def test_ungueltiges_json(self):
        o = skript(b"<html>")
        with self.assertRaises(onvista.DatenFehler):
            onvista.hole_json("https://api.onvista.de/x", oeffnen=o, schlafen=kein_warten)

    def test_nur_https_erlaubt(self):
        with self.assertRaises(onvista.AbrufFehler):
            onvista.hole_bytes("file:///etc/passwd", oeffnen=skript(b""), schlafen=kein_warten)

    def test_antwort_zu_gross(self):
        o = skript(b"x" * 100)
        with self.assertRaises(onvista.AbrufFehler):
            onvista.hole_bytes("https://x.de/", oeffnen=o, schlafen=kein_warten, max_bytes=10)


class TestZertifikat(unittest.TestCase):
    def setUp(self):
        self.z = onvista.parse_zertifikat(lade("zertifikat_snapshot.json"))

    def test_stammdaten(self):
        self.assertEqual(self.z["isin"], "DE000JE3NTM6")
        self.assertEqual(self.z["wkn"], "JE3NTM")
        self.assertEqual(self.z["emittent"], "J.P. Morgan")
        self.assertEqual(self.z["faellig"], "2027-03-19")
        self.assertEqual(self.z["cap"], 142.5)
        self.assertEqual(self.z["bezug"], 1.0)
        self.assertEqual(self.z["basis_name"], "SAP")
        self.assertEqual(self.z["basis_isin"], "DE0007164600")
        self.assertEqual(self.z["basis_art"], "STOCK")

    def test_ids_und_kurse(self):
        self.assertEqual(self.z["entity"], "330631105")
        self.assertEqual(self.z["notation"], 562543634)
        self.assertEqual(self.z["basis_entity"], "82849")
        self.assertEqual(self.z["basis_notation"], 163500)
        self.assertEqual((self.z["z_geld"], self.z["z_brief"]), (140.18, 140.68))

    def test_kennzahlen(self):
        self.assertAlmostEqual(self.z["delta"], 0.0721140435787)
        self.assertAlmostEqual(self.z["theta_tag"], 0.0311432932914)
        self.assertAlmostEqual(self.z["iv"], 47.5977424622)
        self.assertEqual(self.z["max_ertrag_eur"], 2.33)
        self.assertAlmostEqual(self.z["discount_pct"], 33.6546184739)

    def test_kein_discount_zertifikat_ist_fehler(self):
        d = lade("zertifikat_snapshot.json")
        d["derivativesDetails"]["derivativesSubCategory"]["entitySubType"] = "BONUS_CERTIFICATE"
        with self.assertRaises(onvista.DatenFehler):
            onvista.parse_zertifikat(d)

    def test_fehlende_felder_werden_none(self):
        d = lade("zertifikat_snapshot.json")
        del d["derivativesFigure"]["thetaDay"]
        d["quote"]["ask"] = None
        z = onvista.parse_zertifikat(d)
        self.assertIsNone(z["theta_tag"])
        self.assertIsNone(z["z_brief"])

    def test_ohne_basiswert_ist_fehler(self):
        d = lade("zertifikat_snapshot.json")
        d["derivativesUnderlyingList"] = {"list": []}
        with self.assertRaises(onvista.DatenFehler):
            onvista.parse_zertifikat(d)

    def test_handelsdatum_des_zertifikats_berlin(self):
        self.assertEqual(self.z["datum_berlin"], date(2026, 11, 9))


class TestXetra(unittest.TestCase):
    def test_aktie_xetra_nach_prepost(self):
        a = onvista.parse_xetra(lade("aktie_snapshot.json"), "STOCK")
        self.assertEqual(a["notation"], 163500)
        self.assertTrue(a["prepost"])
        self.assertEqual(a["datum_berlin"], date(2026, 11, 9))

    def test_dax(self):
        d = onvista.parse_xetra(lade("dax_snapshot.json"), "INDEX")
        self.assertEqual(d["last"], 26267.19)
        self.assertEqual(d["notation"], 20735)
        self.assertFalse(d["prepost"])

    def test_ohne_xetra_ist_fehler(self):
        d = lade("aktie_snapshot.json")
        d["quoteList"]["list"] = [q for q in d["quoteList"]["list"] if q["market"]["codeMarket"] != "_GER"]
        with self.assertRaises(onvista.DatenFehler):
            onvista.parse_xetra(d, "STOCK")

    def test_berlin_datum_nach_mitternacht_utc(self):
        d = lade("dax_snapshot.json")
        d["quoteList"]["list"][0]["datetimeLast"] = "2026-11-09T23:30:00.000+00:00"
        self.assertEqual(onvista.parse_xetra(d, "INDEX")["datum_berlin"], date(2026, 11, 10))


class TestHistorie(unittest.TestCase):
    def test_parallele_listen_werden_datum_schlusskurs(self):
        h = onvista.parse_historie(lade("hist_zertifikat.json"))
        self.assertEqual(h["2026-11-06"], 140.0)
        self.assertEqual(list(h), sorted(h))

    def test_ungleich_lange_listen_oder_leer(self):
        self.assertEqual(onvista.parse_historie({}), {})
        h = onvista.parse_historie({"datetimeLast": [1793966400, 1794052800], "last": [1.5]})
        self.assertEqual(len(h), 1)

    def test_none_werte_fallen_weg(self):
        h = onvista.parse_historie({"datetimeLast": [1793966400], "last": [None]})
        self.assertEqual(h, {})

    def test_range_waehlt_ausreichende_laenge(self):
        self.assertEqual(onvista.range_fuer(date(2026, 8, 12), date(2026, 9, 1)), "M1")
        self.assertEqual(onvista.range_fuer(date(2026, 8, 12), date(2026, 11, 9)), "M6")
        self.assertEqual(onvista.range_fuer(date(2025, 1, 1), date(2026, 11, 9)), "Y1")

    def test_historie_url(self):
        u = onvista.historie_url("DERIVATIVE", "330631105", 562543634, date(2026, 8, 12), date(2026, 11, 9))
        self.assertEqual(
            u,
            "https://api.onvista.de/api/v1/instruments/DERIVATIVE/330631105/eod_history"
            "?idNotation=562543634&range=M6&startDate=2026-08-12",
        )


if __name__ == "__main__":
    unittest.main()
