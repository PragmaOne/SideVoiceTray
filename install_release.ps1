param(
    [string]$SourceDir = (Join-Path $PSScriptRoot "dist"),
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Programs\SideVoiceTray")
)

$ErrorActionPreference = "Stop"

function Get-LatestBuiltExe {
    param([string]$Dir)

    $candidates = Get-ChildItem -Path $Dir -Filter "SideVoiceTray*.exe" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending
    if (-not $candidates) {
        throw "No SideVoiceTray exe was found in $Dir"
    }
    return $candidates[0]
}

function Test-AppLocked {
    param([string]$TargetExePath)

    $running = Get-Process SideVoiceTray -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -eq [System.IO.Path]::GetFullPath($TargetExePath))
    }
    return $null -ne $running
}

function New-Shortcut {
    param(
        [string]$ShortcutPath,
        [string]$TargetPath,
        [string]$WorkingDirectory
    )

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.Save()
}

$sourceExe = Get-LatestBuiltExe -Dir $SourceDir
$targetExe = Join-Path $InstallDir "SideVoiceTray.exe"
$sourceConfig = Join-Path $SourceDir "config.json"
$sourceModels = Join-Path $SourceDir "models"
$targetConfig = Join-Path $InstallDir "config.json"
$targetModels = Join-Path $InstallDir "models"

if (Test-AppLocked -TargetExePath $targetExe) {
    throw "Installed SideVoiceTray is currently running. Close it from the tray before reinstalling."
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Copy-Item -Path $sourceExe.FullName -Destination $targetExe -Force

if ((Test-Path $sourceConfig) -and -not (Test-Path $targetConfig)) {
    Copy-Item -Path $sourceConfig -Destination $targetConfig -Force
}

if (Test-Path $sourceModels) {
    New-Item -ItemType Directory -Path $targetModels -Force | Out-Null
    Copy-Item -Path (Join-Path $sourceModels "*") -Destination $targetModels -Recurse -Force
}

$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$desktopDir = [Environment]::GetFolderPath("Desktop")
$startMenuShortcut = Join-Path $startMenuDir "SideVoiceTray.lnk"
$desktopShortcut = Join-Path $desktopDir "SideVoiceTray.lnk"

New-Shortcut -ShortcutPath $startMenuShortcut -TargetPath $targetExe -WorkingDirectory $InstallDir
New-Shortcut -ShortcutPath $desktopShortcut -TargetPath $targetExe -WorkingDirectory $InstallDir

Write-Host "Installed to: $InstallDir"
Write-Host "Source exe used: $($sourceExe.FullName)"
