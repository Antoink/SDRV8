@echo off
setlocal
set "APPDIR=C:\Users\antoi\Documents\Pofilage Saison 2026-2027\appV3"

echo ============================================
echo   Lanceur d'applis SDR
echo ============================================
echo.

if not exist "%APPDIR%\venv\Scripts\python.exe" (
    echo ERREUR : python.exe introuvable dans "%APPDIR%\venv\Scripts\"
    echo Le dossier venv a peut-etre ete deplace ou supprime.
    echo.
    pause
    exit /b 1
)

echo Demarrage du serveur dans une nouvelle fenetre...
echo (Cette fenetre-ci va se fermer, c'est normal : regarde la fenetre
echo  intitulee "Lanceur SDR - serveur" qui va s'ouvrir a cote.)
echo.

REM /k garde la nouvelle fenetre ouverte meme si le serveur plante,
REM pour qu'on puisse voir le message d'erreur au lieu qu'elle disparaisse.
start "Lanceur SDR - serveur" /D "%APPDIR%" cmd /k ""%APPDIR%\venv\Scripts\python.exe" -m streamlit run "%APPDIR%\launcher\launcher.py" --server.port 8500"

echo Attente du demarrage (jusqu'a 10 secondes la 1ere fois)...
timeout /t 8 /nobreak >nul

echo Ouverture du navigateur...
start "" "http://localhost:8500"

timeout /t 3
