@echo off
setlocal
cd /d "%~dp0"
title Build kino.exe

echo ============================================================
echo   Building kino.exe
echo ============================================================
echo.

set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto :nopython

if not exist "main.py" goto :nomain
if not exist "icon.ico" goto :noico

if exist "venv\Scripts\python.exe" goto :venv_ok
echo [1/4] Creating virtual environment...
%PY% -m venv venv
if errorlevel 1 goto :fail
goto :venv_done
:venv_ok
echo [1/4] Virtual environment already exists.
:venv_done

call "venv\Scripts\activate.bat"
if errorlevel 1 goto :fail

echo [2/4] Installing pywebview, requests, beautifulsoup4, pyinstaller...
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
python -m pip install --upgrade -r requirements.txt pyinstaller
if errorlevel 1 goto :fail

echo [3/4] Building exe, this can take a few minutes...
pyinstaller --noconsole --onefile --icon icon.ico --add-data "icon.ico;." --clean --noconfirm --name kino --collect-all webview --collect-all clr_loader --collect-all pythonnet --hidden-import bs4 main.py
if errorlevel 1 goto :fail

echo [4/4] Copying result...
if not exist "dist\kino.exe" goto :noexe
copy /Y "dist\kino.exe" "%~dp0kino.exe" >nul

echo.
echo ============================================================
echo   DONE: %~dp0kino.exe
echo   config.json and metadata_cache.json are created next to the exe.
echo ============================================================
echo.
pause
exit /b 0

:nopython
echo [ERROR] Python not found. Install Python 3.12 from https://www.python.org/downloads/
echo         and tick "Add python.exe to PATH".
goto :fail

:nomain
echo [ERROR] main.py not found next to build_exe.bat.
goto :fail

:noico
echo [ERROR] icon.ico not found next to build_exe.bat.
goto :fail

:noexe
echo [ERROR] dist\kino.exe was not created.
goto :fail

:fail
echo.
echo ============================================================
echo   Build failed. Scroll up to see the error.
echo ============================================================
echo.
pause
exit /b 1
