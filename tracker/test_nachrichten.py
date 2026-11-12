"""Tests für tracker/nachrichten.py. Kein Netz: fetch wird ersetzt."""
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from tracker import nachrichten as n
from tracker import onvista

BERLIN = ZoneInfo("Europe/Berlin")


def rss(*items):
    teile = []
    for titel, link, pub, quelle in items:
        teile.append(f"<item><title>{titel}</title><link>{link}</link><pubDate>{pub}</pubDate>"
                     f"<source url='https://q.de'>{quelle}</source></item>")
    return ("<?xml version='1.0' encoding='UTF-8'?><rss version='2.0'><channel><title>x</title>"
            + "".join(teile) + "</channel></rss>").encode("utf-8")


# 09.11.2026 (Montag) 14:09 Berlin = 13:09 GMT
ITEM = ("SAP hebt Prognose an - Handelsblatt", "https://news.google.com/rss/articles/abc",
        "Mon, 09 Nov 2026 13:09:00 GMT", "Handelsblatt")


class TestRss(unittest.TestCase):
    def test_felder_und_quelle_vom_titel_entfernt(self):
        r = n.parse_rss(rss(ITEM))[0]
        self.assertEqual(r["titel"], "SAP hebt Prognose an")
        self.assertEqual(r["quelle"], "Handelsblatt")
        self.assertEqual(r["url"], "https://news.google.com/rss/articles/abc")
        self.assertEqual(r["zeit"], "2026-11-09T14:09:00+01:00")

    def test_nur_https_links(self):
        for link in ("http://x.de/a", "javascript:alert(1)", "//x.de", ""):
            r = n.parse_rss(rss(("T", link, ITEM[2], "Q")))[0]
            self.assertIsNone(r["url"], link)

    def test_doctype_und_entities_werden_abgelehnt(self):
        boese = (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                 b"<rss><channel><item><title>&x;</title></item></channel></rss>")
        with self.assertRaises(n.NachrichtenFehler):
            n.parse_rss(boese)

    def test_zu_gross_wird_abgelehnt(self):
        with self.assertRaises(n.NachrichtenFehler):
            n.parse_rss(b"<rss>" + b"a" * (n.MAX_RSS_BYTES + 1) + b"</rss>")

    def test_kaputtes_xml(self):
        with self.assertRaises(n.NachrichtenFehler):
            n.parse_rss(b"<rss><channel>")

    def test_item_ohne_titel_wird_uebersprungen_und_kein_artikeltext_gespeichert(self):
        xml = (b"<rss><channel><item><link>https://a</link></item>"
               b"<item><title>T</title><description>langer Artikeltext</description></item></channel></rss>")
        r = n.parse_rss(xml)
        self.assertEqual(len(r), 1)
        self.assertNotIn("beschreibung", r[0])
        self.assertEqual(set(r[0]), {"titel", "quelle", "zeit", "url"})


class TestFensterUndAbfrage(unittest.TestCase):
    def test_fenster_dienstag(self):
        von, bis = n.fenster(date(2026, 11, 10))
        self.assertEqual(von, datetime(2026, 11, 9, 17, 35, tzinfo=BERLIN))
        self.assertEqual(bis, datetime(2026, 11, 10, 17, 35, tzinfo=BERLIN))

    def test_wochenende_geht_in_den_montag(self):
        von, _ = n.fenster(date(2026, 11, 9))
        self.assertEqual(von, datetime(2026, 11, 6, 17, 35, tzinfo=BERLIN))

    def test_url(self):
        u = n.url_fuer("SAP Aktie", date(2026, 11, 10))
        self.assertEqual(u, "https://news.google.com/rss/search?q=SAP%20Aktie+after:2026-11-09+before:2026-11-11"
                            "&hl=de&gl=DE&ceid=DE:de")

    def test_begriffe(self):
        self.assertEqual(n.begriffe("SAP", None), ["SAP Aktie", "DAX"])
        self.assertEqual(n.begriffe("SAP", "SAP SE"), ["SAP SE", "DAX"])

    def test_braucht_nachrichten(self):
        heute = date(2026, 11, 20)
        self.assertTrue(n.braucht_nachrichten("2026-11-19", {}, heute))
        self.assertFalse(n.braucht_nachrichten("2026-11-19", {"2026-11-19": []}, heute))
        self.assertFalse(n.braucht_nachrichten("2026-11-05", {}, heute))  # älter als 14 Tage
        self.assertTrue(n.braucht_nachrichten("2026-11-06", {}, heute))


class TestEinordnung(unittest.TestCase):
    def test_kategorien_und_richtung(self):
        faelle = [
            ("SAP übertrifft Erwartungen bei Quartalszahlen", "Quartalszahlen", "positiv"),
            ("Analyst hebt Kursziel für SAP", "Analyst/Kursziel", "positiv"),
            ("SAP: Gewinnwarnung schockt Anleger", "Prognose", "negativ"),
            ("SAP kauft Start-up", "Übernahme/Beteiligung", "neutral"),
            ("SAP kündigt neuen Aktienrückkauf an", "Dividende/Rückkauf", "neutral"),
            ("Klage gegen SAP in den USA", "Recht/Regulierung", "negativ"),
            ("Neuer Finanzchef bei SAP", "Personalie", "neutral"),
            ("EZB senkt Zinsen überraschend", "Makro", "negativ"),
            ("SAP lädt zur Hausmesse ein", "Sonstiges", "neutral"),
            ("DAX erreicht Rekord", "Sonstiges", "positiv"),
        ]
        for titel, kat, richtung in faelle:
            self.assertEqual(n.ordne_ein(titel), (kat, richtung), titel)

    def test_passt_unternehmensnews_zur_aktienrendite(self):
        self.assertTrue(n.passt("Prognose", "positiv", 1.2, -0.5))
        self.assertFalse(n.passt("Prognose", "positiv", -1.2, 0.5))
        self.assertIsNone(n.passt("Prognose", "neutral", 1.2, 0.5))

    def test_passt_makro_zur_dax_rendite(self):
        self.assertTrue(n.passt("Makro", "negativ", 2.0, -1.5))
        self.assertFalse(n.passt("Makro", "negativ", -2.0, 1.5))

    def test_bewerte_top_drei_und_relevanz(self):
        roh = [
            {"titel": "Analyst hebt Kursziel für SAP", "quelle": "A", "zeit": "2026-11-09T10:00:00+01:00", "url": "https://a"},
            {"titel": "Allgemeines über Wetter", "quelle": "B", "zeit": "2026-11-09T11:00:00+01:00", "url": None},
            {"titel": "SAP hebt Prognose an", "quelle": "C", "zeit": "2026-11-09T12:00:00+01:00", "url": "https://c"},
            {"titel": "SAP Hausmesse", "quelle": "D", "zeit": "2026-11-09T13:00:00+01:00", "url": "https://d"},
            {"titel": "Noch ein Wetterbericht", "quelle": "E", "zeit": "2026-11-09T09:00:00+01:00", "url": None},
        ]
        tag = {"aktie_spez_pct": 2.0, "dax_pct": 0.5}
        b = n.bewerte(roh, tag, "SAP")
        self.assertEqual(len(b), 3)
        self.assertEqual({x["titel"] for x in b[:2]}, {"Analyst hebt Kursziel für SAP", "SAP hebt Prognose an"})
        self.assertTrue(all(x["passt"] is True for x in b[:2]))
        self.assertEqual(set(b[0]), {"titel", "quelle", "zeit", "url", "kategorie", "richtung", "passt"})


class TestVerdikt(unittest.TestCase):
    def tag(self, **kw):
        t = {"auffaellig": False, "effekt_markt": 0.1, "effekt_aktie": 0.2, "dax_pct": 0.2, "aktie_spez_pct": 0.3}
        t.update(kw)
        return t

    def news(self, kat, passt):
        return {"kategorie": kat, "passt": passt, "richtung": "positiv" if passt else "neutral"}

    def test_wahrscheinlicher_zusammenhang(self):
        v = n.verdikt(self.tag(auffaellig=True), [self.news("Prognose", True)])
        self.assertEqual(v, "Wahrscheinlicher Zusammenhang")

    def test_marktbewegung_durch_dax_anteil(self):
        self.assertEqual(n.verdikt(self.tag(effekt_markt=0.5, effekt_aktie=0.1), []), "Marktbewegung")

    def test_marktbewegung_durch_makro_treffer(self):
        self.assertEqual(n.verdikt(self.tag(), [self.news("Makro", True)]), "Marktbewegung")

    def test_marktbewegung_bei_grosser_dax_aenderung(self):
        self.assertEqual(n.verdikt(self.tag(dax_pct=-1.8), []), "Marktbewegung")

    def test_moeglicher_zusammenhang(self):
        v = n.verdikt(self.tag(auffaellig=True), [self.news("Prognose", None)])
        self.assertEqual(v, "Möglicher Zusammenhang")

    def test_normales_rauschen(self):
        self.assertEqual(n.verdikt(self.tag(), []), "Im normalen Rauschen")

    def test_keine_erklaerung(self):
        self.assertEqual(n.verdikt(self.tag(auffaellig=True), []), "Keine Erklärung gefunden")

    def test_ohne_analyse_kein_verdikt(self):
        self.assertIsNone(n.verdikt({"auffaellig": None}, []))


class TestSammeln(unittest.TestCase):
    def test_sammelt_filtert_fenster_dedupliziert(self):
        xml = rss(ITEM, ITEM, ("Alt", "https://x", "Fri, 06 Nov 2026 10:00:00 GMT", "Q"))
        aufrufe = []

        def fetch(url):
            aufrufe.append(url)
            return xml

        erg = n.sammle(["2026-11-09"], {}, date(2026, 11, 9), fetch, "SAP", None, pause=lambda: None)
        self.assertEqual(len(aufrufe), 2)
        self.assertEqual([x["titel"] for x in erg["2026-11-09"]], ["SAP hebt Prognose an"])

    def test_fehler_brechen_nie_ab(self):
        def fetch(url):
            raise onvista.AbrufFehler("kaputt")

        erg = n.sammle(["2026-11-09"], {}, date(2026, 11, 9), fetch, "SAP", None, pause=lambda: None)
        self.assertEqual(erg, {})  # nichts speichern, damit der nächste Lauf es erneut versucht

    def test_sperre_beendet_weitere_abfragen(self):
        aufrufe = []

        def fetch(url):
            aufrufe.append(url)
            raise onvista.GesperrtFehler("429")

        erg = n.sammle(["2026-11-09", "2026-11-10"], {}, date(2026, 11, 10), fetch, "SAP", None, pause=lambda: None)
        self.assertEqual(len(aufrufe), 1)
        self.assertEqual(erg, {})

    def test_vorhandene_tage_werden_nicht_erneut_abgefragt(self):
        def fetch(url):
            raise AssertionError("kein Abruf erwartet")

        erg = n.sammle(["2026-11-09"], {"2026-11-09": []}, date(2026, 11, 9), fetch, "SAP", None, pause=lambda: None)
        self.assertEqual(erg, {})

    def test_pro_tag_werden_hoechstens_max_gespeichert_relevante_zuerst(self):
        items = [(f"Wetter {i}", f"https://x/{i}", "Mon, 09 Nov 2026 13:09:00 GMT", "Q") for i in range(n.MAX_GESPEICHERT + 10)]
        items.append(("SAP hebt Prognose an", "https://x/sap", "Mon, 09 Nov 2026 13:09:00 GMT", "Q"))
        erg = n.sammle(["2026-11-09"], {}, date(2026, 11, 9), lambda url: rss(*items), "SAP", None, pause=lambda: None)
        self.assertEqual(len(erg["2026-11-09"]), n.MAX_GESPEICHERT)
        self.assertEqual(erg["2026-11-09"][0]["titel"], "SAP hebt Prognose an")

    def test_eine_abfrage_ok_reicht_zum_speichern(self):
        xml = rss(ITEM)
        zaehler = {"n": 0}

        def fetch(url):
            zaehler["n"] += 1
            if zaehler["n"] == 1:
                raise onvista.AbrufFehler("x")
            return xml

        erg = n.sammle(["2026-11-09"], {}, date(2026, 11, 9), fetch, "SAP", None, pause=lambda: None)
        self.assertIn("2026-11-09", erg)


if __name__ == "__main__":
    unittest.main()
