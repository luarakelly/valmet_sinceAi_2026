@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Backend environment not found. Run initialize.bat first.
    exit /b 1
)

cd /d "%BACKEND_DIR%"
"%PYTHON%" -m uvicorn app.main:app --reload
