@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "VENV_DIR=%BACKEND_DIR%\.venv"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv is required. Install it from https://docs.astral.sh/uv/ and run this script again.
    exit /b 1
)

echo Creating or updating the backend uv environment...
uv venv "%VENV_DIR%"
if errorlevel 1 exit /b 1
uv pip install --python "%VENV_DIR%\Scripts\python.exe" -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 exit /b 1

if not exist "%ROOT_DIR%.env" (
    copy /Y "%ROOT_DIR%.env.example" "%ROOT_DIR%.env" >nul
    echo Created .env from .env.example. Add your API key before using Gemini.
) else (
    echo .env already exists; leaving it unchanged.
)

echo Initialization complete. Start the backend with run.bat
exit /b 0
