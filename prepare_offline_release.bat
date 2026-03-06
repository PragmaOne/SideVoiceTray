@echo off
setlocal
cd /d %~dp0

if not exist .venv (
  python -m venv .venv
)

set PYTHON_EXE=%~dp0.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" (
  echo Python virtual environment is not available.
  exit /b 1
)

call build_exe.bat
if errorlevel 1 exit /b 1

"%PYTHON_EXE%" download_whisper_model.py --model large-v3 --output-dir dist\models
if errorlevel 1 exit /b 1

if exist config.json (
  copy /Y config.json dist\config.json >nul
) else (
  copy /Y config.example.json dist\config.json >nul
)

echo.
echo Offline release prepared in: dist
endlocal
