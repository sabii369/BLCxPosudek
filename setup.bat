@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   Bridge Load Calculator - instalace potrebnych balicku
echo ============================================================
echo.

rem --- najdi Python (python nebo spoustec py) ---
set "PY="
python --version >nul 2>&1 && set "PY=python"
if not defined PY (
    py -3 --version >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    echo [CHYBA] Python nebyl nalezen.
    echo Nainstalujte Python 3 z https://www.python.org/downloads/
    echo a pri instalaci zaskrtnete "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)
echo Pouzity Python:
%PY% --version
echo.

echo [1/3] Aktualizace pip ...
%PY% -m pip install --upgrade pip
echo.

echo [2/3] Instalace balicku: numpy, scipy, matplotlib, openpyxl ...
%PY% -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
    echo.
    echo [CHYBA] Instalace balicku selhala - zkontrolujte pripojeni k internetu
    echo nebo spustte setup.bat znovu jako spravce.
    pause
    exit /b 1
)
echo.

echo [3/3] Kontrola instalace ...
%PY% -c "import numpy, scipy, matplotlib, openpyxl; print('numpy', numpy.__version__, '| scipy', scipy.__version__, '| matplotlib', matplotlib.__version__, '| openpyxl', openpyxl.__version__)"
if errorlevel 1 (
    echo [CHYBA] Nektery balicek se nepodarilo nacist.
    pause
    exit /b 1
)
%PY% -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo [VAROVANI] Chybi tkinter ^(graficke rozhrani^). Preinstalujte Python z python.org
    echo            a nechte zaskrtnutou volbu "tcl/tk and IDLE".
) else (
    echo tkinter: OK
)
echo.
echo Hotovo. Program spustte souborem spustit.bat.
echo.
pause
