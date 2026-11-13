# Discount-Tracker: Vorgabe

Täglicher Kursspeicher für ein Discount-Zertifikat, seinen Basiswert (DAX-Aktie) und den DAX. Erklärt Kursänderungen regelbasiert, **ohne LLM und ohne bezahlte API** (0 Tokens im Betrieb). Läuft 10 Wochen auf GitHub Actions in einem eigenen privaten Repo. Python 3.12+, außer `openpyxl` und `tzdata` nur Standardbibliothek.

Wechsel des Zertifikats: nur `config.json` ändern. Daten liegen je ISIN getrennt.

## Dateien

```
config.json            {"isin": "DE000JE3NTM6", "demo": true, "start": "2026-11-10", "wochen": 10, "basis_suchbegriff": null}
lauf.py                Einstieg: python lauf.py [--neu-bauen]  (--neu-bauen: ohne Netz, nur Auswertung/Ausgabe neu)
tracker/onvista.py     Abruf und Umwandlung in Datensätze
tracker/speicher.py    CSV/JSONL lesen, zusammenführen; Wochenschnitte
tracker/analyse.py     Beta, Zerlegung in Effekte, Auffälligkeit, Erklärungstext
tracker/nachrichten.py Google-News-RSS: Abruf, Einordnung, Zuordnung zum Handelstag
tracker/excel.py       ausgabe/kurse.xlsx
tracker/seite.py       setzt daten in tracker/vorlage.html ein → ausgabe/index.html
tracker/vorlage.html   Dashboard (Agent Design), installierbar als App
tracker/app/           manifest.webmanifest, sw.js, Icons (seite.py kopiert sie neben index.html); icons_erzeugen.py erzeugt die PNGs
daten/<ISIN>/kurse.csv, nachrichten.jsonl, meta.json
ausgabe/index.html, ausgabe/kurse.xlsx, ausgabe/daten.json, ausgabe/status.json
.github/workflows/taeglich.yml, .github/workflows/seite.yml, requirements.txt, oeffnen.bat, .gitignore, README.md
```
Tests neben dem Modul: `tracker/test_<modul>.py`, `unittest`, Netz immer gemockt (Fixtures unter `tracker/testdaten/`). TDD: Test rot, dann grün. Ziel 80 % Kernlogik. Dateien 200–400 Zeilen, Funktionen < 50 Zeilen. Konstanten oben mit Quelle.

## Datenquelle onvista (Abruf getestet am 09.11.2026)

User-Agent ehrlich: `discount-tracker/1.0 (privat)`. Kein Umgehen von Sperren, keine Proxys, kein Browser-Vortäuschen. Bei 403/429: Abbruch mit klarer Meldung. Timeout 20 s, 2 Wiederholungen bei 5xx/Netzfehler. Höchstens ein erfolgreicher Tagesabruf: liegt die Zeile für heute schon vollständig vor, ohne Netz beenden.

Basis: `https://api.onvista.de/api/v1`
- Zertifikat: `GET /derivatives/ISIN:{isin}/snapshot`
  - `instrument.name|wkn|isin|entityValue`; `quote.bid|ask|last|datetimeLast`, `quote.market.idNotation` (Emittenten-Notierung, die nehmen)
  - `derivativesIssuer.name`; `derivativesDetails.datetimeMaturity`, `.derivativesSubCategory.entitySubType` (muss `DISCOUNT_CERTIFICATE` sein, sonst Fehler)
  - `derivativesFigure.deltaBid|thetaDay|impliedVolatilityAsk|theoreticalValue|maximumEarningBid|maximumEarningBidPct|discountPct`
  - `derivativesUnderlyingList.list[0]`: `.instrument.entityValue|isin|name|entityType`, `.market.idNotation`, `.coverRatio`, `.derivativesBarrierList.list[]` mit `typeBarrier == "CAP"` → `.barrier`
- Basiswert: `GET /stocks/ISIN:{isin}/snapshot`, Xetra-Eintrag aus `quoteList.list` (`market.codeMarket == "_GER"`), Felder `last`, `datetimeLast`
- DAX: `GET /indices/ISIN:DE0008469008/snapshot`, Xetra-Eintrag aus `quoteList.list` (`market.name == "Xetra"`, idNotation 20735, entityValue 20735)
- Historie: `GET /instruments/{STOCK|INDEX|DERIVATIVE}/{entityValue}/eod_history?idNotation={n}&range=M1&startDate=YYYY-MM-DD`. Antwort: parallele Listen `datetimeLast` (Unix-Sekunden, 12:00 UTC), `first`, `last`, `high`, `low`. Längere `range`-Werte (M3, M6, Y1) einmal prüfen, sonst mehrere M1-Abrufe. Zertifikats-Historie endet einen Tag früher als Aktien-Historie.

Abfolge eines Laufs: Snapshot Zertifikat → Historie Zertifikat/Basiswert/DAX ab `start − 90 Tage` (Lücken füllen, auch verpasste Tage) → heutige Zeile aus Snapshots → Nachrichten → Auswertung → Ausgabe. Handelstag = Datum (Europe/Berlin) des Xetra-`datetimeLast` des Basiswerts; ist es nicht heute: keine heutige Zeile (Feiertag). Nach Laufende (`start + wochen*7 − 1`, also 18.01.2027): Meldung, keine Abrufe, Exit 0.

## kurse.csv

Spalten, ein Handelstag je Zeile, sortiert, Punkt als Dezimaltrenner:
`datum,z_geld,z_brief,z_quelle,basis,dax,delta,theta_tag,iv`
`z_quelle` = `snapshot` oder `historie`. Bei `historie` ist `z_geld` der Schlusswert der Emittenten-Notierung, `z_brief`, `delta`, `theta_tag`, `iv` bleiben leer. Bestehende Werte nie überschreiben, nur Leeres füllen. Fehlt ein Wert: Feld leer, Zeile trotzdem speichern.

## Analyse (analyse.py, reine Funktionen)

Für jeden Tag t mit Vortag t−1 (nur Zeilen mit allen drei Kursen):
- `z_pct, basis_pct, dax_pct` in Prozent. `dz = z_t − z_{t-1}` in €.
- `beta`: Regression der Basiswert- auf DAX-Tagesrenditen, 60 Tage rollierend vor t, mindestens 20 Punkte, sonst 1,0 mit `beta_geschaetzt=true`.
- `delta` = Wert aus t, sonst letzter bekannter (auch später bekannter) Wert, sonst Näherung 0,5 mit `delta_geschaetzt=true`.
- `effekt_basis = delta * bezug * (S_t − S_{t-1})`
- `effekt_markt = delta * bezug * S_{t-1} * beta * dax_ret`; `effekt_aktie = effekt_basis − effekt_markt`
- `effekt_zeit = theta_tag * Kalendertage seit t−1` (theta positiv = Zertifikat gewinnt Zeitwert; fehlt: letzter bekannter)
- `effekt_rest = dz − effekt_basis − effekt_zeit` (Spread, Volatilität, Zinsen, Dividendenerwartung)
- `haupttreiber`: betragsgrößter unter markt/aktie/zeit/rest, Namen „DAX-Bewegung“, „Aktie selbst“, „Zeitwert“, „Sonstiges (Spread, Vola, Zinsen)“
- `auffaellig`: |aktienspez. Rendite| / Std.-Abw. der aktienspez. Renditen der 60 Tage davor ≥ 1,5 (`z_score`, null bei < 20 Punkten)
- `spruenge`: Liste `{wert, pct, schwelle}` für jeden Kurs, dessen Tagesänderung betragsmäßig ≥ Schwelle ist. Schwellen in % (`daten.SPRUNG_PCT`, Quelle: Std.-Abw. der Tagesrenditen 12.08.–12.11.2026): Zertifikat 2, Basiswert 5, DAX 3; überschreibbar mit `config.json` → `sprung_pct` (Schlüssel `z`, `basis`, `dax`, Werte > 0 bis 100). Dashboard: Vermerk am Tag und Marke „Sprung“ in der Tagesliste; Excel: Spalte „Kurssprung“.
- `cap_abstand_pct = (S − Cap)/Cap*100`. Über dem Cap und Delta klein ⇒ Satz: Zertifikat nahe Höchstwert, Aktienbewegungen kommen kaum an.

`text` (reines Deutsch, 2–4 kurze Sätze, keine Fachkürzel ohne Erklärung; Zahlen deutsch formatiert): Was passierte mit Zertifikat in € und %; Bewegung der Aktie, davon DAX-Anteil; wie viel durch Delta ankam; Zeitwert; Haupttreiber.

## Nachrichten

Google News RSS, zwei Abfragen je Handelstag (nur für Tage ohne gespeicherte Nachrichten und höchstens die letzten 14 Tage):
`https://news.google.com/rss/search?q={Begriff}+after:{t-1}+before:{t+1}&hl=de&gl=DE&ceid=DE:de`, Begriff 1: `basis_suchbegriff` oder `"<Basisname> Aktie"`, Begriff 2: `DAX`. Felder `title`, `link`, `pubDate`, `source`. Titel ohne angehängte Quelle. Fehler hier brechen den Lauf nie ab. Nur Titel, Quelle, Zeit, Link speichern, keinen Artikeltext.

Fenster eines Handelstags: Xetra-Schluss des Vortags (17:35 Berlin) bis 17:35 am Tag t, Wochenenden gehen in den Montag.
Einordnung per Stichwort, Konstanten-Tabelle:
- `kategorie`: Quartalszahlen, Prognose, Analyst/Kursziel, Übernahme/Beteiligung, Dividende/Rückkauf, Recht/Regulierung, Personalie, Makro (EZB, Zins, Inflation, Zoll, Konjunktur), Sonstiges
- `richtung`: positiv/negativ/neutral aus Wörtern (hebt, erhöht, übertrifft, Kurssprung, Rekord / senkt, verfehlt, Gewinnwarnung, bricht ein, Absturz, Klage)
- `passt`: `true`, wenn Richtung zur Bewegung passt (Unternehmensnews zur aktienspez. Rendite, Makro/DAX-Treffer zur DAX-Rendite), `false` gegenläufig, `null` neutral
- `relevanz`: Name im Titel, Kategorie ≠ Sonstiges, passt, Top 3 je Tag
`verdikt`: `"Wahrscheinlicher Zusammenhang"` (auffällig und mind. eine passende Unternehmensnews), `"Marktbewegung"` (|DAX-Anteil| > |Aktienanteil|, Makro-Treffer oder große DAX-Änderung), `"Möglicher Zusammenhang"` (auffällig, News ohne klare Richtung), `"Im normalen Rauschen"` (nicht auffällig), `"Keine Erklärung gefunden"` (auffällig, keine News). Nie als Beweis formulieren; Zusatz in der Oberfläche: zeitlicher Zusammenhang, kein Beweis.

## Wochenschnitte

ISO-Woche, Mittelwert der Tageskurse z_geld, basis, dax, dazu `tage`, `von`, `bis`, Änderung des Schnitts zur Vorwoche in % (`z_vorwoche_pct`). Je Kurs zusätzlich Wochenschluss (`z_schluss`, `basis_schluss`, `dax_schluss`: letzter vorhandene Wert der Woche) und Änderung Schluss zu Vorwochenschluss (`z_woche_pct`, `basis_woche_pct`, `dax_woche_pct`); Bezug der ersten Woche ist der letzte Schluss vor `start`, ohne Vorlauf `null`. Nur Zeilen ab `start`, unvollständige Woche mit `tage < 5` kennzeichnen.

## daten.json (Vertrag zwischen Logik und Dashboard)

Gesamtobjekt (mehrere Zertifikate, Reihenfolge wie `config.json`):

```json
{"stand": "<neuester Abruf>", "repo": "besitzer/name", "konfig": "<Fingerabdruck von config.json>",
 "zertifikate": [<Objekt je Zertifikat, siehe unten>],
 "status": {"ok": true, "meldung": "", "letzter_lauf": "...", "je_zertifikat": {"<ISIN>": {"ok": true, "meldung": ""}}}}
```
`status.json` = `status` des Gesamtobjekts. Ändert sich `config.json`, baut der nächste Lauf `ausgabe/` neu, auch wenn heute schon abgerufen wurde (Vergleich über `konfig`). Je Zertifikat liegt der letzte Abrufstatus in `daten/<ISIN>/status.json`.

Objekt je Zertifikat:

```json
{
  "stand": "2026-11-09T18:40:00+01:00",
  "produkt": {"isin":"","wkn":"","name":"","emittent":"","cap":142.5,"bezug":1.0,"faellig":"2027-03-19","basis_name":"SAP","basis_isin":"","demo":true,"lauf_start":"2026-11-10","lauf_ende":"2027-01-18"},
  "aktuell": {"z_geld":140.17,"z_brief":140.67,"max_ertrag_eur":2.33,"max_ertrag_pct":1.66,"delta":0.07,"discount_pct":33.65,"cap_abstand_pct":48.5,
             "seit_start":{"bezug_datum":"2026-11-09","z_eur":0.03,"z_pct":0.02,"basis_pct":0.43,"dax_pct":1.92}},
  "fortschritt": {"tag":1,"tage_gesamt":70,"woche":1},
  "tage": [{
    "datum":"2026-11-09","phase":"vorlauf","z_geld":140.17,"z_brief":140.67,"z_quelle":"snapshot","basis":211.65,"dax":26267.19,
    "z_pct":0.12,"basis_pct":0.43,"dax_pct":1.73,"dz":0.17,"delta":0.07,"beta":1.1,"effekt_markt":0.3,"effekt_aktie":-0.2,"effekt_zeit":0.03,"effekt_rest":0.04,
    "haupttreiber":"DAX-Bewegung","auffaellig":false,"z_score":0.4,"text":"…","verdikt":"Im normalen Rauschen",
    "nachrichten":[{"titel":"","quelle":"","zeit":"2026-11-09T14:09:00+01:00","url":"https://…","kategorie":"Analyst/Kursziel","richtung":"positiv","passt":true}]
  }],
  "wochen": [{"woche":"2026-W46","von":"2026-11-10","bis":"2026-11-13","tage":4,"z_schnitt":140.2,"basis_schnitt":212.0,"dax_schnitt":26200.0,"z_vorwoche_pct":null,
              "z_schluss":140.17,"basis_schluss":212.55,"dax_schluss":26771.88,"z_woche_pct":0.02,"basis_woche_pct":0.43,"dax_woche_pct":1.92}],
  "status": {"ok":true,"meldung":"","letzter_lauf":"2026-11-09T18:40:00+01:00"}
}
```
`seit_start`: letzter Schluss vor `start` bis zum letzten bekannten Kurs; ohne Vorlauf alle Felder `null`. `--neu-bauen` übernimmt `stand` aus `meta.json` (Zeit des letzten Abrufs).
`phase` = `vorlauf` (vor `start`, höchstens 30 Kalendertage anzeigen) oder `lauf`. Felder dürfen `null` sein; Dashboard muss das aushalten.

`seite.py`: ersetzt in `vorlage.html` genau den Platzhalter `/*__DATEN__*/null` durch JSON mit maskiertem `<`, `>`, `&`, U+2028, U+2029 (`<` → `<` usw.), damit Schlagzeilen kein Skript einschleusen können.

## Excel

Gesamtdatei (`schreibe_gesamt`): „Übersicht“ (eine Spalte je Zertifikat: Stammdaten, Kurs, Seit Start, Max. Ertrag, Discount, Abstand zum Cap, Handelstage, Status; darunter Quelle und Abrufzeit), dann je Zertifikat „<WKN> Tage“, „<WKN> Wochen“, „<WKN> Erklärungen“ (ohne WKN die ISIN). Einzeldatei (`schreibe`, nur Tests): Blätter: „Tageskurse“ (Datum echt, Zertifikat Geld/Brief, Basiswert, DAX, % je Tag, Phase), „Wochenschnitte“, „Erklärungen“ (Datum, Text, Verdikt, Top-Nachricht), „Info“ (Stammdaten, Quelle, Abrufzeit). Kopfzeile fixiert, Autofilter, deutsche Zahlenformate, Spaltenbreiten, nativer Linien-Chart für Zertifikat und Wochenschnitt.

## App (GitHub Pages)

`seite.yml` lädt `ausgabe/` als Pages-Seite hoch: nach jedem Lauf von „Kurse abrufen“ (`workflow_run`, auch bei rotem Lauf, dann zeigt die Seite die Störung), bei Pushes auf `ausgabe/**` und von Hand. Voraussetzung: Repo öffentlich, unter Settings → Pages die Quelle „GitHub Actions“. Service Worker: zuerst Netz, ohne Netz der zuletzt geladene Stand; neue Fassung über `CACHE` in `sw.js`.

Seite: Menü oben (Übersicht, je Zertifikat ein Eintrag, Suchen), Hash-Routen `#/`, `#/z/<ISIN>`, `#/suche`. Übersicht = Tabelle mit fester erster Spalte und einer Spalte je Zertifikat (am Handy seitlich scrollbar). Suche filtert die verfolgten Zertifikate; eine gültige WKN/ISIN fragt auf Knopfdruck den onvista-Snapshot direkt aus dem Browser ab (CORS erlaubt) und bietet einen vorbereiteten Issue-Link an. Skripte: `tracker/app/logik.js` (reine Logik, `node --test`), `ansicht.js` (Detailansicht), `app.js` (Menü, Übersicht, Suche); `seite.py` bettet sie ein. Content-Security-Policy als Meta-Tag: Netz nur zur eigenen Seite und `api.onvista.de`.

## Zertifikat verwalten (Issue)

`zertifikat-verwalten.yml` startet bei `issues: opened/reopened`, nur wenn Autor = Repo-Besitzer (`author_association OWNER`) und der Titel mit `Zertifikat ` beginnt. Titel nur über die Umgebungsvariable `ISSUE_TITLE` an `verwalten.py`. Erlaubt: `^Zertifikat (hinzufügen|entfernen): ([A-Z0-9]{6}|[A-Z0-9]{12})$`, ISIN mit Prüfziffer. Hinzufügen: onvista-Snapshot per WKN/ISIN, nur `DISCOUNT_CERTIFICATE`, Start heute (Berlin), 10 Wochen, dann `lauf.py --isin`. Entfernen: aus `config.json`, Daten bleiben, Ausgabe neu ohne Netz. Antwort als Issue-Kommentar, bei Erfolg Issue schließen. Gleiche Concurrency-Gruppe `kurse` wie der tägliche Lauf.

## Workflow

Cron `50 16 * * 1-5` und `40 20 * * 1-5` (UTC, also 17:50 und 21:40 Berlin im Winter; zweiter Lauf ist Sicherung), dazu `workflow_dispatch`. `permissions: contents: write`, `actions/checkout@v4`, `actions/setup-python@v5` mit Python 3.12. `git add daten ausgabe`, Commit nur bei Änderung mit `daten: Kurse <datum>`, Autor github-actions[bot]. Fehlgeschlagener Abruf ⇒ `status.json` mit Meldung wird trotzdem committet, dann Job rot.
