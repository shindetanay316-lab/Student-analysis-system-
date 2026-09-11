@echo off
setlocal

if not exist .venv (
    py -3 -m venv .venv
    if errorlevel 1 exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

if not exist .env copy .env.example .env >nul

python seed.py
if errorlevel 1 exit /b 1

echo.
echo Setup complete. Edit .env, then run: .venv\Scripts\python app.py
endlocal
