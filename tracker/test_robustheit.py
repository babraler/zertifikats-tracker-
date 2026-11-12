"""Tests zu den Review-Funden: unmögliche Kurse, unerwartete Fehler, unklarer Handelstag, Zeitbudget."""
import json
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from tracker import analyse, nachrichten as n, onvista, speicher
from tracker.test_lauf import Basis, Router

BERLIN = ZoneInfo("Europe/Berlin")
LEER_RSS = b"<?xml version='1.0'?><rss><channel></channel></rss>"


class TestUnmoeglicheKurse(unittest.TestCase):
    def test_historie_verwirft_null_und_negativ(self):
        ts = [1762732800, 1762819200, 1762905600]
        self.assertEqual(len(onvista.parse_historie({"datetimeLast": ts, "last": [0, -1.5, 10.0]})), 1)

    def test_xetra_kurs_null_gilt_als_fehlend(self):
        d = {"instrument": {}, "quoteList": {"list": [{"last": 0, "market": {"codeMarket": "_GER"}}]}}
        self.assertIsNone(onvista.parse_xetra(d, "STOCK")["last"])

    def test_analyse_zaehlt_null_nicht_als_vollstaendig(self):
        self.assertFalse(analyse._vollstaendig({"z_geld": 1.0, "basis": 0.0, "dax": 1.0}))
        self.assertTrue(analyse._vollstaendig({"z_geld": 1.0, "basis": 2.0, "dax": 1.0}))

    def test_lies_kurse_verwirft_null_nan_und_inf(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "k.csv"
            p.write_text("datum,z_geld,z_brief,z_quelle,basis,dax,delta,theta_tag,iv\n"
                         "2026-11-09,0,nan,snapshot,inf,-3,-0.2,0.1,\n", encoding="utf-8")
            z = speicher.lies_kurse(p)["2026-11-09"]
        self.assertEqual((z["z_geld"], z["z_brief"], z["basis"], z["dax"]), (None, None, None, None))
        self.assertEqual(z["delta"], -0.2)   # Kennzahlen dürfen negativ sein


class TestSpeichern(unittest.TestCase):
    def test_tempdatei_wird_bei_fehler_entfernt(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "k.csv"
            with mock.patch("tracker.speicher.os.replace", side_effect=PermissionError):
                with self.assertRaises(PermissionError):
                    speicher._atomar_schreiben(p, b"x")
            self.assertEqual(os.listdir(t), [])


class TestZeit(unittest.TestCase):
    def test_zeitstempel_ohne_zone_gilt_als_utc(self):
        self.assertEqual(onvista._berlin_datum("2026-11-09T23:30:00"), date(2026, 11, 10))


class TestUnerwarteteFehler(Basis):
    def status(self):
        return json.loads(self.pfad("ausgabe", "status.json").read_text(encoding="utf-8"))

    def test_fehler_im_abruf_landet_im_status(self):
        with mock.patch("lauf.onvista.lade_alles", side_effect=KeyError("x")):
            self.assertEqual(self.lauf(Router()), 1)
        self.assertFalse(self.status()["ok"])
        self.assertIn("KeyError", self.status()["meldung"])

    def test_fehler_in_der_auswertung_landet_im_status(self):
        with mock.patch("lauf.daten_modul.baue_daten", side_effect=TypeError("x")):
            self.assertEqual(self.lauf(Router()), 1)
        self.assertFalse(self.status()["ok"])

    def test_excel_fehler_bricht_den_lauf_nicht_ab(self):
        with mock.patch("lauf.excel.schreibe", side_effect=ValueError("x")):
            self.assertEqual(self.lauf(Router()), 0, self.out)
        self.assertTrue(self.pfad("ausgabe", "daten.json").exists())

    def test_null_in_der_csv_blockiert_neu_bauen_nicht(self):
        self.lauf(Router())
        t = self.csv().read_text(encoding="utf-8").replace(",210.75,", ",0,")   # Vortag: alter Kurs 0 bricht die Rendite
        self.csv().write_text(t, encoding="utf-8")
        self.assertEqual(self.lauf(Router(), ["--neu-bauen"]), 0, self.out)


class RouterOhneAktienDatum(Router):
    def antwort(self, url):
        b = super().antwort(url)
        if "/stocks/" not in url:
            return b
        d = json.loads(b)
        for q in d["quoteList"]["list"]:
            q["datetimeLast"] = None
        return json.dumps(d).encode("utf-8")


class TestUnklarerHandelstag(Basis):
    def test_sicherungslauf_versucht_es_erneut(self):
        jetzt = datetime(2026, 11, 10, 18, 40, tzinfo=BERLIN)
        self.lauf(RouterOhneAktienDatum(), jetzt=jetzt)
        r2 = Router()
        self.lauf(r2, jetzt=datetime(2026, 11, 10, 21, 40, tzinfo=BERLIN))
        self.assertNotEqual(r2.urls, [])


class TestNachrichtenBudget(unittest.TestCase):
    TAGE = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]

    def test_bricht_nach_fehltagen_in_folge_ab(self):
        urls = []

        def fetch(url):
            urls.append(url)
            raise n.AbrufFehler("x")

        n.sammle(self.TAGE, {}, date(2026, 11, 6), fetch, "SAP", None, pause=lambda: None)
        self.assertEqual(len(urls), n.MAX_FEHLTAGE_IN_FOLGE * len(n.begriffe("SAP", None)))

    def test_bricht_nach_zeitbudget_ab(self):
        urls, zeit = [], iter(range(0, 100000, n.MAX_SEKUNDEN - 1))

        def fetch(url):
            urls.append(url)
            return LEER_RSS

        n.sammle(self.TAGE, {}, date(2026, 11, 6), fetch, "SAP", None, pause=lambda: None, uhr=lambda: next(zeit))
        self.assertEqual(len(urls), len(n.begriffe("SAP", None)))


if __name__ == "__main__":
    unittest.main()
