@echo off
rem BLC x Posudek PB - most -> zatizeni nosniku z obalek -> posudek predpjateho nosniku
rem Dvojklik = GUI s prikladem; pretazeni souboru .toml na tento soubor = GUI se souborem.
cd /d "%~dp0"
set "PY=python"
python --version >nul 2>&1 || set "PY=py -3"
if "%~1"=="" goto bez_souboru
%PY% -m blc_posudek "%~1" --gui
goto konec
:bez_souboru
%PY% -m blc_posudek
:konec
if errorlevel 1 pause
