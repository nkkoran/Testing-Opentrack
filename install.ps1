# HeadMouse one-step install / update. Press Win+R, paste this line and press Enter:
#
#   powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/nkkoran/Testing-Opentrack/master/install.ps1 | iex"
#
# Normally downloads the latest HeadMouse-Setup.exe from the GitHub Releases page and runs
# it (no Python needed; keeps settings when updating; starts HeadMouse when done).
# If no release exists yet, falls back to installing from source into
# %LOCALAPPDATA%\HeadMouse and running tools\setup.ps1.
# Works in Windows PowerShell 5.1.

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"

$repo = "nkkoran/Testing-Opentrack"
$branch = "master"
$target = if ($env:HEADMOUSE_TARGET) { $env:HEADMOUSE_TARGET } else { Join-Path $env:LOCALAPPDATA "HeadMouse" }
$keep = @("headmouse_settings.toml", "face_landmarker.task")

if (-not $env:HEADMOUSE_ZIP) {
    $installer = Join-Path ([IO.Path]::GetTempPath()) "HeadMouse-Setup.exe"
    try {
        Write-Host "Downloading HeadMouse..." -ForegroundColor Cyan
        Invoke-WebRequest "https://github.com/$repo/releases/latest/download/HeadMouse-Setup.exe" `
            -OutFile $installer -UseBasicParsing
        Write-Host "Installing HeadMouse - it starts by itself when done."
        Start-Process -FilePath $installer -ArgumentList "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait
        Remove-Item $installer -ErrorAction SilentlyContinue
        return
    } catch {
        Write-Host "No ready-made installer found - installing from source instead."
    }
}

try {
    Write-Host "Downloading HeadMouse source..." -ForegroundColor Cyan
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("headmouse-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $zip = Join-Path $tmp "headmouse.zip"
    if ($env:HEADMOUSE_ZIP) {
        Copy-Item -LiteralPath $env:HEADMOUSE_ZIP -Destination $zip
    } else {
        Invoke-WebRequest "https://github.com/$repo/archive/refs/heads/$branch.zip" -OutFile $zip -UseBasicParsing
    }
    Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $tmp "x")
    $source = Get-ChildItem -LiteralPath (Join-Path $tmp "x") -Directory | Select-Object -First 1

    # Keep the player's settings (and the downloaded face model) when updating.
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    foreach ($name in $keep) {
        $existing = Join-Path $target $name
        if (Test-Path -LiteralPath $existing) {
            Remove-Item -LiteralPath (Join-Path $source.FullName $name) -ErrorAction SilentlyContinue
        }
    }
    # File by file: Copy-Item -Recurse can nest folders instead of merging when they exist.
    $base = $source.FullName.TrimEnd('\', '/').Length + 1
    foreach ($file in Get-ChildItem -LiteralPath $source.FullName -Recurse -File) {
        $dest = Join-Path $target $file.FullName.Substring($base)
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $dest -Force
    }
    Remove-Item -LiteralPath $tmp -Recurse -Force
    Write-Host "HeadMouse files are in $target"

    if (-not $env:HEADMOUSE_NO_SETUP) {
        & (Join-Path $target "tools\setup.ps1")
    }
} catch {
    Write-Host ""
    Write-Host "HeadMouse could not be installed: $_" -ForegroundColor Red
    Write-Host "Check the internet connection and try again."
    Read-Host "Press Enter to close"
}
