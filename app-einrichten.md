# Discount-Tracker als App einrichten

Kosten: 0 €. GitHub Pages ist für öffentliche Repos kostenlos (https://docs.github.com/en/pages/getting-started-with-github-pages/about-github-pages). Dauer für dich: etwa 5 Minuten.

## Was öffentlich wird

Code, Börsenkurse (onvista), Schlagzeilen mit Link (Google News) und die ISIN des beobachteten Zertifikats. Keine Kaufkurse, keine Stückzahl, keine Kontodaten. Deine iCloud-Adresse habe ich vorher aus allen Commits entfernt und durch die GitHub-Ersatzadresse ersetzt.

## Dein Teil

1. **E-Mail schützen:** https://github.com/settings/emails → „Keep my email addresses private“ und „Block command line pushes that expose my email“ anhaken. Sonst steht bei Änderungen über die GitHub-Webseite wieder deine iCloud-Adresse im Repo.
2. **Alten Testlauf löschen:** https://github.com/babraler/zertifikats-tracker-/actions → Lauf „#1 Kurse abrufen“ → „…“ → „Delete workflow run“. Er verweist noch auf die alten Commits mit der iCloud-Adresse.
3. **Repo öffentlich stellen:** https://github.com/babraler/zertifikats-tracker-/settings → ganz unten „Danger Zone“ → „Change visibility“ → „Make public“.
4. **Pages einschalten:** https://github.com/babraler/zertifikats-tracker-/settings/pages → „Source“ auf **GitHub Actions** stellen.
5. Mir Bescheid geben. Ich lade dann den neuen Stand hoch und prüfe, ob die Seite läuft.

## Danach am Handy

Adresse: https://babraler.github.io/zertifikats-tracker-/

- iPhone: in Safari öffnen → Teilen → „Zum Home-Bildschirm“.
- Android: in Chrome öffnen → Menü → „App installieren“.

Die App holt bei jedem Öffnen den neuesten Stand. Ohne Netz zeigt sie den zuletzt geladenen.

Neue Zertifikate fügst du in der App unter „Suchen“ hinzu (WKN oder ISIN). Das Absenden läuft über ein GitHub-Issue, dafür im Browser bei GitHub angemeldet sein. Nach etwa 2 Minuten steht das Zertifikat in der App.
