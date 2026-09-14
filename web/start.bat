@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set VENV_PYTHON=%~dp0..\.venv\Scripts\python.exe

if not exist "%VENV_PYTHON%" (
    echo Creating virtual environment...
    py -3.12 -m venv "%~dp0..\.venv"
    call "%VENV_PYTHON%" -m pip install --upgrade pip
    call "%VENV_PYTHON%" -m pip install -r requirements.txt
)

echo Starting Shot Management System...
echo.

call "%VENV_PYTHON%" app.py

pause
