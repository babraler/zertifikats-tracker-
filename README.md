# Discount-Tracker

Täglicher Kursspeicher für ein Discount-Zertifikat, seinen Basiswert und den DAX. Erklärt Kursänderungen regelbasiert, ohne LLM und ohne bezahlte API (0 Tokens im Betrieb). Vorgabe: `SPEC.md`.

## Einrichten (einmalig, Windows)

```
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Benutzen

- `.venv\Scripts\python lauf.py` ruft heute ab (höchstens ein erfolgreicher Abruf pro Tag), wertet aus und baut `ausgabe/`.
- `.venv\Scripts\python lauf.py --neu-bauen` baut ohne Netz nur Auswertung und Ausgabe neu.
- `oeffnen.bat` baut neu und öffnet `ausgabe/index.html`.
- Tests: `.venv\Scripts\python -m unittest discover -s tracker -t .`

## Zertifikat wechseln

Nur `config.json` ändern (`isin`, `start`, `wochen`, optional `basis_suchbegriff`). Daten liegen je ISIN getrennt unter `daten/<ISIN>/`.

## Ergebnis

`ausgabe/index.html` (Dashboard), `kurse.xlsx`, `daten.json`, `status.json`. Das Dashboard liest nur `daten.json` (Vertrag in `SPEC.md`).

## App am Handy

Adresse: https://babraler.github.io/zertifikats-tracker-/ (nach dem Einrichten, siehe `app-einrichten.md`). Aktualisiert sich nach jedem Lauf selbst, auch wenn der PC aus ist. Ohne Netz zeigt die App den zuletzt geladenen Stand.

- iPhone: Adresse in Safari öffnen → Teilen → „Zum Home-Bildschirm“.
- Android: Adresse in Chrome öffnen → Menü → „App installieren“.

Lokal testen: `python -m http.server 4420 --directory ausgabe`, dann http://localhost:4420 (unter `file://` läuft der Service Worker nicht).

## GitHub Actions

`.github/workflows/taeglich.yml` läuft werktags um 18:40 und 21:40 Uhr Berlin (Winterzeit; zweiter Lauf als Sicherung). Es ruft ab, committet `daten` und `ausgabe` nur bei Änderung und führt danach die Tests aus, damit ein roter Test keine Tagesdaten kostet. Schlägt der Abruf fehl, wird `status.json` mit der Meldung trotzdem committet und der Job wird rot. Hinweis: Im Sommer (MESZ) verschieben sich die UTC-Zeiten um eine Stunde nach vorn, die Cron-Zeiten müssen dann auf 16:40 und 19:40 UTC stehen. Nach dem Laufende ruft das Skript nichts mehr ab; den Workflow dann unter Actions deaktivieren.

## Hinweise

- Datenquelle onvista mit ehrlichem User-Agent. Bei 403/429 bricht der Lauf mit klarer Meldung ab, nichts wird umgangen.
- Schlagzeilen (Google News RSS) zeigen einen zeitlichen Zusammenhang, keinen Beweis. Je Tag werden höchstens 30 gespeichert.
- Nach dem Xetra-Schluss ist der Aktienkurs im Snapshot ein Nachbörsenwert; gespeichert wird dann der Schlusskurs aus der Historie.
- Messfehler an der Nahtstelle: Tage vor dem ersten Abruf und nachgefüllte Tage nutzen den Schlusskurs der Historie, abgerufene Tage den Geldkurs. Beim Übergang landet die Differenz in „Sonstiges“.
