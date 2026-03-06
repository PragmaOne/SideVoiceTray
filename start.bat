@echo off
cd /d %~dp0
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
if not exist .venv (
  python -m venv .venv
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
set NVIDIA_CUBLAS_BIN=%~dp0.venv\Lib\site-packages\nvidia\cublas\bin
if exist "%NVIDIA_CUBLAS_BIN%" set PATH=%NVIDIA_CUBLAS_BIN%;%PATH%
echo Starting SideVoiceTray from source...
".venv\Scripts\python.exe" -u run.py
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo SideVoiceTray exited with code %EXIT_CODE%.
  pause
)
