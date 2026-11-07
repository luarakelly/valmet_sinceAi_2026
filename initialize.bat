@echo off
setlocal

rem One-time setup: backend virtual environment + dependencies + .env (with or without uv).
set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "VENV_DIR=%BACKEND_DIR%\.venv"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"

if exist "%PYTHON%" (
    echo Using existing environment: %VENV_DIR%
) else (
    where uv >nul 2>nul
    if not errorlevel 1 (
        echo Creating environment with uv...
        uv venv "%VENV_DIR%" || exit /b 1
    ) else (
        echo Creating environment with py -3 -m venv...
        py -3 -m venv "%VENV_DIR%" || python -m venv "%VENV_DIR%" || exit /b 1
    )
)

echo Installing backend dependencies (first time can take several minutes)...
where uv >nul 2>nul
if not errorlevel 1 (
    uv pip install --python "%PYTHON%" -r "%BACKEND_DIR%\requirements.txt" || exit /b 1
) else (
    "%PYTHON%" -m pip install --upgrade pip
    "%PYTHON%" -m pip install -r "%BACKEND_DIR%\requirements.txt" || exit /b 1
)

if not exist "%ROOT_DIR%.env" (
    copy /Y "%ROOT_DIR%.env.example" "%ROOT_DIR%.env" >nul
    echo Created .env from .env.example. Add GEMINI_API_KEY to enable the LLM narrative.
) else (
    echo .env already exists; leaving it unchanged.
)

echo Initialization complete. Start the server with run.bat
exit /b 0
