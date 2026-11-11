@echo off
setlocal
cd /d "%~dp0"
title Kino

set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto :nopython

if exist "venv\Scripts\pythonw.exe" if exist "venv\.deps_ok" goto :run

echo First launch: installing components (1-2 minutes, internet required)...
if not exist "venv\Scripts\python.exe" (
    %PY% -m venv venv
    if errorlevel 1 goto :fail
)
"venv\Scripts\python.exe" -m pip install --upgrade pip
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail
echo ok> "venv\.deps_ok"

:run
start "" "venv\Scripts\pythonw.exe" "%~dp0main.py"
exit /b 0

:nopython
echo [ERROR] Python not found. Install Python 3.10+ from https://www.python.org/downloads/
echo         and tick "Add python.exe to PATH". Then run this file again.
goto :fail

:fail
echo.
echo Launch failed. Scroll up to see the error.
pause
exit /b 1
