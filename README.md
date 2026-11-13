# Discount-Tracker

Täglicher Kursspeicher für bis zu 10 Discount-Zertifikate, ihre Basiswerte und den DAX. Erklärt Kursänderungen regelbasiert, ohne LLM und ohne bezahlte API (0 Tokens im Betrieb). Vorgabe: `SPEC.md`.

## Einrichten (einmalig, Windows)

```
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Benutzen

- `.venv\Scripts\python lauf.py` ruft heute alle Zertifikate ab (je Zertifikat höchstens ein erfolgreicher Abruf pro Tag), wertet aus und baut `ausgabe/`. `--isin <ISIN>` ruft nur eines ab.
- `.venv\Scripts\python lauf.py --neu-bauen` baut ohne Netz nur Auswertung und Ausgabe neu.
- `oeffnen.bat` baut neu und öffnet `ausgabe/index.html`.
- Tests: `.venv\Scripts\python -m unittest discover -s tracker -t .` und `node --test tracker/app/logik.test.mjs`

## Zertifikate verwalten

**Für andere Nutzer:** Menü „Suchen“ → WKN oder ISIN eingeben → „bei onvista nachsehen“ → „Hinzufügen anfragen“. Das teilt WKN und ISIN per Nachricht an den Betreiber. Alle teilen sich dieselben 10 Plätze.

**Betreiber:** Gleicher Weg, dann „Über GitHub hinzufügen (Betreiber)“. Das öffnet ein vorbereitetes Issue (`Zertifikat hinzufügen: <ISIN>`); absenden genügt, dafür bei GitHub angemeldet sein. Der Workflow `zertifikat-verwalten.yml` prüft das Zertifikat bei onvista (nur Discount-Zertifikate), trägt es mit Start heute und 10 Wochen ein, holt die ersten Kurse, baut die App neu und antwortet im Issue. Entfernen geht genauso über „Entfernen“ (`Zertifikat entfernen: <ISIN>`); die Kurse bleiben unter `daten/<ISIN>/`. Nur Issues des Repo-Besitzers zählen. Kommt nach 5 Minuten kein Kommentar, das Issue schließen und wieder öffnen.

**Von Hand:** `config.json`:

```json
{"repo": "babraler/zertifikats-tracker-",
 "sprung_pct": {"z": 2, "basis": 5, "dax": 3},
 "zertifikate": [{"isin": "DE000JE3NTM6", "start": "2026-11-10", "wochen": 10, "demo": false, "basis_suchbegriff": null}]}
```

`sprung_pct` sind die Schwellen in % für den Vermerk „Kurssprung“ (global, je Zertifikat überschreibbar). Das alte Format mit nur einem Zertifikat wird weiter gelesen. Höchstens 10 Zertifikate, damit die Abrufe bei onvista klein bleiben (3 s Pause zwischen zwei Zertifikaten).

## Ergebnis

`ausgabe/index.html` (App mit Menü: je Zertifikat eine eigene Übersicht, dazu Suchen; die App öffnet das zuletzt gewählte Zertifikat; „Link teilen“ führt direkt auf ein Zertifikat, `#/z/<ISIN>`), `kurse.xlsx` (Blatt „Übersicht“ plus je Zertifikat Tage, Wochen, Erklärungen), `daten.json` (alle Zertifikate), `status.json` (Gesamtstatus plus `je_zertifikat`). Die App-Skripte liegen in `tracker/app/*.js` und werden in `index.html` eingebettet.

## App am Handy

Adresse: https://babraler.github.io/zertifikats-tracker-/ (nach dem Einrichten, siehe `app-einrichten.md`). Aktualisiert sich nach jedem Lauf selbst, auch wenn der PC aus ist. Ohne Netz zeigt die App den zuletzt geladenen Stand.

- iPhone: Adresse in Safari öffnen → Teilen → „Zum Home-Bildschirm“.
- Android: Adresse in Chrome öffnen → Menü → „App installieren“.

Lokal testen: `python -m http.server 4420 --directory ausgabe`, dann http://localhost:4420 (unter `file://` läuft der Service Worker nicht).

## GitHub Actions

`.github/workflows/taeglich.yml` läuft werktags um 17:50 und 21:40 Uhr Berlin (Winterzeit; zweiter Lauf als Sicherung). Es ruft ab, committet `daten` und `ausgabe` nur bei Änderung und führt danach die Tests aus, damit ein roter Test keine Tagesdaten kostet. Schlägt der Abruf fehl, wird `status.json` mit der Meldung trotzdem committet und der Job wird rot. Hinweis: Im Sommer (MESZ) verschieben sich die UTC-Zeiten um eine Stunde nach vorn, die Cron-Zeiten müssen dann auf 15:50 und 19:40 UTC stehen. Nach dem Laufende ruft das Skript nichts mehr ab; den Workflow dann unter Actions deaktivieren.

## Hinweise

- Datenquelle onvista mit ehrlichem User-Agent. Bei 403/429 bricht der Lauf mit klarer Meldung ab, nichts wird umgangen.
- Schlagzeilen (Google News RSS) zeigen einen zeitlichen Zusammenhang, keinen Beweis. Je Tag werden höchstens 30 gespeichert.
- Nach dem Xetra-Schluss ist der Aktienkurs im Snapshot ein Nachbörsenwert; gespeichert wird dann der Schlusskurs aus der Historie.
- Messfehler an der Nahtstelle: Tage vor dem ersten Abruf und nachgefüllte Tage nutzen den Schlusskurs der Historie, abgerufene Tage den Geldkurs. Beim Übergang landet die Differenz in „Sonstiges“.
