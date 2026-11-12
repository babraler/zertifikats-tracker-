@echo off
rem Holt den neuesten Stand von GitHub und oeffnet das Dashboard.
rem Ohne GitHub-Anbindung wird die Seite lokal neu gebaut.
cd /d "%~dp0"
git remote get-url origin >nul 2>&1
if errorlevel 1 goto lokal
echo Hole den neuesten Stand von GitHub ...
git pull --ff-only
if errorlevel 1 (
  echo.
  echo Aktualisieren hat nicht geklappt. Du siehst den letzten Stand auf diesem PC.
  pause
)
goto oeffnen

:lokal
if not exist ".venv\Scripts\python.exe" (
  echo Keine .venv gefunden. Einmalig: py -3 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
.venv\Scripts\python lauf.py --neu-bauen

:oeffnen
if exist "ausgabe\index.html" (start "" "ausgabe\index.html") else (echo index.html fehlt, siehe Meldung oben. & pause)
