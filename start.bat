@echo off
chcp 65001 >nul
title Forestly - ukladanie opisow (konfiguracja)
echo.
echo   Forestly - ukladanie opisow: konfiguracja / pierwsze uruchomienie
echo   -------------------------------------------------------------
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo   Nie znaleziono Pythona. Zainstaluj Python 3 z python.org
  echo   ^(przy instalacji zaznacz "Add Python to PATH"^).
  echo.
  pause
  exit /b 1
)
python -c "import webview" >nul 2>nul
if errorlevel 1 (
  echo   Instaluje biblioteke okna ^(pywebview^) - chwilka...
  python -m pip install --quiet --upgrade pywebview
)
echo   Gotowe. Uruchamiam program bez okna cmd...
start "" pythonw "%~dp0uklad_app.py"
exit /b 0
