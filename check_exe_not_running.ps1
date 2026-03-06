param(
    [Parameter(Mandatory = $true)]
    [string]$AppName,
    [Parameter(Mandatory = $true)]
    [string]$ExePath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ExePath)) {
    exit 0
}

$target = [System.IO.Path]::GetFullPath((Resolve-Path $ExePath).Path)
$running = Get-Process -Name $AppName -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -eq $target)
}

if ($running) {
    Write-Host "The target exe is running. Close it from the tray before rebuilding: $target"
    exit 1
}
