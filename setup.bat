@echo off
echo ====================================================
echo   Digital Twin AI - Milestone 1 Setup Script
echo ====================================================
echo.

REM Check if Python is installed
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.9+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

python --version
echo.

REM Create virtual environment
echo Creating virtual environment...
python -m venv venv
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)
echo Virtual environment created.
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo.
echo ====================================================
echo   Dependencies installed successfully!
echo ====================================================
echo.
echo NEXT STEPS:
echo 1. Download your Firebase service account key:
echo    Firebase Console ^> Project Settings ^> Service Accounts
echo    ^> Generate new private key ^> Save as serviceAccountKey.json
echo    Place it in: %CD%
echo.
echo 2. Copy .env.example to .env (already done if .env exists):
echo    copy .env.example .env
echo.
echo 3. Run the application:
echo    venv\Scripts\activate
echo    python run.py
echo.
echo 4. Open browser at: http://localhost:5000
echo.
pause
