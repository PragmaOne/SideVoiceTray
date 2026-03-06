@echo off
setlocal
cd /d %~dp0

set APP_NAME=SideVoiceTray
if not "%~1"=="" set APP_NAME=%~1

if exist "dist\%APP_NAME%.exe" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_exe_not_running.ps1" -AppName "%APP_NAME%" -ExePath "%~dp0dist\%APP_NAME%.exe"
  if errorlevel 1 exit /b 1
)

if not exist .venv (
  python -m venv .venv
)

set PYTHON_EXE=%~dp0.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" (
  echo Python virtual environment is not available.
  exit /b 1
)

"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r requirements.txt pyinstaller

"%PYTHON_EXE%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name %APP_NAME% ^
  --collect-all faster_whisper ^
  --collect-all ctranslate2 ^
  --collect-submodules pynput ^
  --collect-submodules pystray ^
  --collect-submodules sounddevice ^
  --collect-binaries nvidia.cublas ^
  run.pyw

if errorlevel 1 exit /b 1

if exist config.json (
  copy /Y config.json dist\config.json >nul
) else (
  copy /Y config.example.json dist\config.json >nul
)

echo.
echo Built: dist\%APP_NAME%.exe
endlocal
