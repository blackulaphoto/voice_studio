@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Athena Voice Studio is not set up yet.
  echo Run setup.bat first, then run start.bat again.
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo Frontend packages are missing. Running pnpm install...
  pushd frontend
  call pnpm install
  popd
)

echo Starting Athena Voice API on http://127.0.0.1:8000 ...
start "Athena Voice API" cmd /k "cd /d "%~dp0backend" && "%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

timeout /t 2 /nobreak >nul

echo Starting Athena Voice Studio on http://127.0.0.1:5173 ...
start "Athena Voice Studio" cmd /k "cd /d "%~dp0frontend" && pnpm dev"

echo.
echo Athena Voice Studio is starting. Open http://127.0.0.1:5173 in your browser.
endlocal
