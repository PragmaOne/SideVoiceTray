param(
    [string]$Version = "6.4.3",
    [string]$InstallDir = (Join-Path $PSScriptRoot "tools\Inno Setup 6")
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$downloadUrl = "https://files.jrsoftware.org/is/6/innosetup-$Version.exe"
$tempInstaller = Join-Path $env:TEMP "innosetup-$Version.exe"

if (Test-Path (Join-Path $InstallDir "ISCC.exe")) {
    Write-Host "Inno Setup already installed at: $InstallDir"
    exit 0
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Invoke-WebRequest -Uri $downloadUrl -OutFile $tempInstaller -TimeoutSec 300

$arguments = @(
    "/SP-",
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/CURRENTUSER",
    "/DIR=`"$InstallDir`""
)

$process = Start-Process -FilePath $tempInstaller -ArgumentList $arguments -Wait -PassThru
if ($process.ExitCode -ne 0) {
    throw "Inno Setup installer failed with exit code $($process.ExitCode)"
}

if (-not (Test-Path (Join-Path $InstallDir "ISCC.exe"))) {
    throw "Inno Setup installation completed but ISCC.exe was not found in $InstallDir"
}

Write-Host "Inno Setup installed at: $InstallDir"
