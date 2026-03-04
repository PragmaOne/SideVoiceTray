@echo off
cd /d %~dp0
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate
pip install -r requirements.txt
set NVIDIA_CUBLAS_BIN=%~dp0.venv\Lib\site-packages\nvidia\cublas\bin
if exist "%NVIDIA_CUBLAS_BIN%" set PATH=%NVIDIA_CUBLAS_BIN%;%PATH%
python run.py
