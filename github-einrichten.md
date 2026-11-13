# Discount-Tracker auf GitHub bringen

Dauer: etwa 2 Minuten. Kosten: voraussichtlich 0 €. Private Repos haben ein monatliches Freikontingent für Actions (https://docs.github.com/en/actions/concepts/billing-and-usage). Der Tracker braucht rund 45 Minuten im Monat (Annahme: 2 Läufe je Werktag à 1 Minute). Die Höhe des Kontingents für deinen Tarif steht unter GitHub → Settings → Billing. Annahme: rund 2.000 Minuten im kostenlosen Tarif, die Zahl konnte ich auf der aktuellen Doku-Seite nicht bestätigen.

## Dein Teil

1. https://github.com/new öffnen.
2. Name: `discount-tracker`. Sichtbarkeit: **Private**.
3. Kein README, keine .gitignore, keine Lizenz ankreuzen. Das Repo muss leer sein.
4. „Create repository“ klicken und mir die Adresse schicken, z. B. `https://github.com/DEINNAME/discount-tracker`.

## Mein Teil danach

1. Lokales Repo an die Adresse hängen und hochladen. Beim ersten Mal öffnet sich einmalig ein GitHub-Anmeldefenster, die Anmeldung machst du selbst.
2. Testlauf starten. Er zeigt, ob onvista Abrufe von GitHub-Servern zulässt. Am PC geht das, von GitHub aus ist es noch ungetestet.
3. Wird GitHub gesperrt, nehme ich die Ausgabeseite des Emittenten als Plan B. Eine Sperre wird nicht umgangen.

## Dein Zertifikat eintragen

Sobald du es ausgesucht hast, reicht mir die ISIN. Ich trage sie in `config.json` ein (`isin`, `demo: false`, `start`). Bis dahin läuft das J.P.-Morgan-Beispiel auf SAP, im Dashboard als „Beispiel-Zertifikat“ markiert.

## Täglicher Betrieb

- GitHub ruft werktags um 17:50 Uhr ab, um 21:40 Uhr läuft die Sicherung. Dein PC kann aus sein.
- Doppelklick auf `oeffnen.bat` holt den neuesten Stand und öffnet das Dashboard. Die Excel-Datei liegt daneben: `ausgabe/kurse.xlsx`.
