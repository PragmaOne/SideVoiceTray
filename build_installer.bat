@echo off
setlocal
cd /d %~dp0

call prepare_offline_release.bat
if errorlevel 1 exit /b 1

set "ISCC_EXE="
if exist "%~dp0tools\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%~dp0tools\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC_EXE (
  echo Inno Setup Compiler was not found. Installing a local copy...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_innosetup_local.ps1"
  if errorlevel 1 exit /b 1

  if exist "%~dp0tools\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%~dp0tools\Inno Setup 6\ISCC.exe"
  if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"

  if not defined ISCC_EXE (
    echo Inno Setup installation finished, but ISCC.exe was still not found.
    exit /b 1
  )
)

"%ISCC_EXE%" SideVoiceTray.iss
if errorlevel 1 exit /b 1

echo.
echo Installer built in: installer-dist
endlocal
