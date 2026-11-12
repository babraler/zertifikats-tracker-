"""Tests für lauf.py (Ablauf Ende-zu-Ende, Netz komplett gemockt)."""
import contextlib
import io
import json
import tempfile
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import lauf

BERLIN = ZoneInfo("Europe/Berlin")
DATEN = Path(__file__).parent / "testdaten"
CONFIG = {"isin": "DE000JE3NTM6", "demo": True, "start": "2026-11-10", "wochen": 10, "basis_suchbegriff": None}
RSS = ("<?xml version='1.0'?><rss><channel><item><title>SAP hebt Prognose an - Handelsblatt</title>"
       "<link>https://news.google.com/a</link><pubDate>Mon, 09 Nov 2026 13:09:00 GMT</pubDate>"
       "<source>Handelsblatt</source></item></channel></rss>").encode("utf-8")
VORLAGE = "<html><script>const DATEN = /*__DATEN__*/null;</script></html>"


class FakeAntwort:
    def __init__(self, b):
        self.b = b

    def read(self, n=-1):
        return self.b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Router:
    """Ersetzt urlopen: liefert Fixtures je Adresse und zählt die Abrufe."""

    def __init__(self, fehler=None, news=RSS):
        self.urls, self.fehler, self.news = [], fehler or {}, news

    def antwort(self, url):
        for teil, code in self.fehler.items():
            if teil in url:
                raise urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(b""))
        if "news.google.com" in url:
            return self.news
        tabelle = [("/derivatives/", "zertifikat_snapshot.json"), ("/stocks/", "aktie_snapshot.json"),
                   ("/indices/", "dax_snapshot.json"), ("/DERIVATIVE/", "hist_zertifikat.json"),
                   ("/STOCK/", "hist_aktie.json"), ("/INDEX/", "hist_dax.json")]
        for teil, datei in tabelle:
            if teil in url:
                return (DATEN / datei).read_bytes()
        raise AssertionError("unerwartete Adresse " + url)

    def __call__(self, req, timeout=None):
        self.urls.append(req.full_url)
        return FakeAntwort(self.antwort(req.full_url))


class Basis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = Path(self.tmp.name)
        (self.w / "config.json").write_text(json.dumps(CONFIG), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def lauf(self, router, args=(), jetzt=datetime(2026, 11, 9, 18, 40, tzinfo=BERLIN)):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(out):
            code = lauf.main(list(args), jetzt=jetzt, oeffnen=router, schlafen=lambda s: None, wurzel=self.w)
        self.out = out.getvalue()
        return code

    def pfad(self, *teile):
        return self.w.joinpath(*teile)

    def csv(self):
        return self.pfad("daten", "DE000JE3NTM6", "kurse.csv")


class TestErsterLauf(Basis):
    def test_dateien_entstehen_und_werte_stimmen(self):
        r = Router()
        self.assertEqual(self.lauf(r), 0, self.out)
        for p in (("ausgabe", "daten.json"), ("ausgabe", "status.json"), ("ausgabe", "kurse.xlsx"),
                  ("daten", "DE000JE3NTM6", "kurse.csv"), ("daten", "DE000JE3NTM6", "meta.json"),
                  ("daten", "DE000JE3NTM6", "nachrichten.jsonl")):
            self.assertTrue(self.pfad(*p).exists(), p)
        zeilen = self.csv().read_text(encoding="utf-8").splitlines()
        heute = [z for z in zeilen if z.startswith("2026-11-09")][0].split(",")
        self.assertEqual(heute[1:4], ["140.18", "140.68", "snapshot"])
        self.assertEqual(heute[4], "211.65")      # Schlusskurs aus der Historie, nicht der Nachbörsenwert 212.75
        self.assertEqual(heute[5], "26267.19")
        self.assertTrue(any(z.startswith("2026-11-06") and ",historie," in z for z in zeilen))

    def test_status_und_daten_json(self):
        self.lauf(Router())
        status = json.loads(self.pfad("ausgabe", "status.json").read_text(encoding="utf-8"))
        self.assertTrue(status["ok"])
        d = json.loads(self.pfad("ausgabe", "daten.json").read_text(encoding="utf-8"))
        self.assertEqual(d["produkt"]["basis_name"], "SAP")
        self.assertEqual(d["tage"][-1]["datum"], "2026-11-09")
        self.assertEqual(d["tage"][-1]["nachrichten"][0]["titel"], "SAP hebt Prognose an")

    def test_fehlende_vorlage_bricht_nicht_ab(self):
        self.assertEqual(self.lauf(Router()), 0)
        self.assertIn("vorlage.html", self.out)
        self.assertFalse(self.pfad("ausgabe", "index.html").exists())

    def test_mit_vorlage_entsteht_index(self):
        (self.w / "tracker").mkdir()
        (self.w / "tracker" / "vorlage.html").write_text(VORLAGE, encoding="utf-8")
        self.lauf(Router())
        self.assertIn("DE000JE3NTM6", self.pfad("ausgabe", "index.html").read_text(encoding="utf-8"))

    def test_nur_erlaubte_adressen_und_ehrlicher_agent(self):
        r = Router()
        self.lauf(r)
        self.assertTrue(all(u.startswith(("https://api.onvista.de/", "https://news.google.com/")) for u in r.urls))
        self.assertEqual(sum("eod_history" in u for u in r.urls), 3)


class TestZweiterLauf(Basis):
    def test_zweiter_lauf_am_selben_tag_ohne_abruf_und_csv_unveraendert(self):
        self.lauf(Router())
        vorher = self.csv().read_bytes()
        r2 = Router()
        self.assertEqual(self.lauf(r2, jetzt=datetime(2026, 11, 9, 21, 40, tzinfo=BERLIN)), 0)
        self.assertEqual(r2.urls, [])
        self.assertEqual(self.csv().read_bytes(), vorher)

    def test_feiertag_wird_nur_einmal_abgerufen(self):
        jetzt = datetime(2026, 11, 10, 18, 40, tzinfo=BERLIN)   # Fixtures zeigen Handelstag 09.11.
        self.lauf(Router(), jetzt=jetzt)
        self.assertNotIn("2026-11-10", self.csv().read_text(encoding="utf-8"))
        r2 = Router()
        self.lauf(r2, jetzt=jetzt)
        self.assertEqual(r2.urls, [])


class TestSonderfaelle(Basis):
    def test_neu_bauen_ohne_netz(self):
        self.lauf(Router())
        self.pfad("ausgabe", "daten.json").unlink()
        r = Router()
        self.assertEqual(self.lauf(r, ["--neu-bauen"]), 0)
        self.assertEqual(r.urls, [])
        self.assertTrue(self.pfad("ausgabe", "daten.json").exists())

    def test_neu_bauen_behaelt_zeit_des_letzten_abrufs(self):
        self.lauf(Router())
        abruf = json.loads(self.pfad("ausgabe", "daten.json").read_text(encoding="utf-8"))["stand"]
        self.lauf(Router(), ["--neu-bauen"], jetzt=datetime(2026, 11, 12, 23, 59, tzinfo=BERLIN))
        d = json.loads(self.pfad("ausgabe", "daten.json").read_text(encoding="utf-8"))
        self.assertEqual((d["stand"], d["status"]["letzter_lauf"]), (abruf, abruf))
        self.assertEqual(d["fortschritt"]["tag"], 3)  # Fortschritt nach dem echten Datum des Neubaus

    def test_nach_laufende_keine_abrufe_exit_null(self):
        r = Router()
        code = self.lauf(r, jetzt=datetime(2027, 1, 19, 18, 40, tzinfo=BERLIN))
        self.assertEqual((code, r.urls), (0, []))
        self.assertIn("Laufende", self.out)

    def test_sperre_schreibt_status_und_gibt_fehlercode(self):
        code = self.lauf(Router(fehler={"/stocks/": 429}))
        self.assertEqual(code, 1)
        status = json.loads(self.pfad("ausgabe", "status.json").read_text(encoding="utf-8"))
        self.assertFalse(status["ok"])
        self.assertIn("429", status["meldung"])

    def test_nachrichtenfehler_brechen_nicht_ab(self):
        self.assertEqual(self.lauf(Router(fehler={"news.google.com": 503})), 0)
        self.assertTrue(json.loads(self.pfad("ausgabe", "status.json").read_text(encoding="utf-8"))["ok"])

    def test_ungueltige_config(self):
        for kaputt in ({**CONFIG, "isin": "../../x"}, {**CONFIG, "start": "morgen"}, {**CONFIG, "wochen": 0}, {"isin": "x"}):
            (self.w / "config.json").write_text(json.dumps(kaputt), encoding="utf-8")
            self.assertEqual(self.lauf(Router()), 2, kaputt)

    def test_unveraenderte_daten_bei_wiederholung_nach_neu_bauen(self):
        self.lauf(Router())
        vorher = self.csv().read_bytes()
        self.lauf(Router(), ["--neu-bauen"])
        self.assertEqual(self.csv().read_bytes(), vorher)


if __name__ == "__main__":
    unittest.main()
