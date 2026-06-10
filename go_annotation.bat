@echo off
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

"%PYTHON%" annotate_assets.py %*
if errorlevel 1 pause
