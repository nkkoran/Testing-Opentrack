# HeadMouse setup. Installs Python if needed, HeadMouse's parts, the face model and
# desktop / Start-menu shortcuts, then starts HeadMouse. Safe to run again (it repairs
# and updates). Started by Setup.bat or by install.ps1. Works in Windows PowerShell 5.1.
param([switch]$NoLaunch)

# "Continue", not "Stop": in Windows PowerShell 5.1, "Stop" turns any text a program
# writes to stderr into a fatal error. Failures are checked explicitly instead.
$ErrorActionPreference = "Continue"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"  # the progress bar makes downloads very slow in 5.1
$Root = Split-Path -Parent $PSScriptRoot
$Versions = @("3.13", "3.12", "3.11", "3.14")   # preferred first; all have MediaPipe support
$VcRedistUrl = "https://aka.ms/vs/17/release/vc_redist.x64.exe"

function Step($n, $text) {
    Write-Host ""
    Write-Host "[$n/5] $text" -ForegroundColor Cyan
}

function Test-Python($exe) {
    if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { return $false }
    if ($exe -like "*\WindowsApps\*") { return $false }   # Microsoft Store placeholder, not real Python
    & $exe -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 14) else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Find-Python {
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($v in $Versions) {
            $exe = & $py.Source "-$v" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and (Test-Python "$exe".Trim())) { return "$exe".Trim() }
        }
    }
    foreach ($v in $Versions) {
        $folder = "Python" + $v.Replace(".", "")
        foreach ($base in @("$env:LOCALAPPDATA\Programs\Python", $env:ProgramFiles)) {
            if (-not $base) { continue }
            $exe = Join-Path (Join-Path $base $folder) "python.exe"
            if (Test-Python $exe) { return $exe }
        }
    }
    return $null
}

function Update-PathFromRegistry {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
                "$env:LOCALAPPDATA\Programs\Python\Launcher"
}

function Get-PythonInstallerUrl {
    # Newest Python 3.13.x that has a Windows installer on python.org.
    $listing = (Invoke-WebRequest "https://www.python.org/ftp/python/" -UseBasicParsing).Content
    $found = [regex]::Matches($listing, 'href="(3\.13\.\d+)/"') | ForEach-Object { [version]$_.Groups[1].Value }
    foreach ($v in ($found | Sort-Object -Descending -Unique)) {
        $url = "https://www.python.org/ftp/python/$v/python-$v-amd64.exe"
        try {
            Invoke-WebRequest $url -Method Head -UseBasicParsing -ErrorAction Stop | Out-Null
            return $url
        } catch { }
    }
    throw "No Python installer was found on python.org."
}

function Install-Python {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "Installing Python 3.13 (this takes a minute or two)..."
        & $winget.Source install --id Python.Python.3.13 --exact --scope user --silent `
            --accept-package-agreements --accept-source-agreements --disable-interactivity
        Update-PathFromRegistry
        $exe = Find-Python
        if ($exe) { return $exe }
        Write-Host "winget did not finish the job - downloading Python from python.org instead."
    }
    $url = Get-PythonInstallerUrl
    $file = Join-Path $env:TEMP (Split-Path $url -Leaf)
    Write-Host "Downloading $url ..."
    Invoke-WebRequest $url -OutFile $file -UseBasicParsing
    Write-Host "Installing Python (this takes a minute or two)..."
    Start-Process -FilePath $file -Wait -ArgumentList @(
        "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1",
        "InstallLauncherAllUsers=0", "Include_tcltk=1", "Include_test=0")
    Remove-Item $file -ErrorAction SilentlyContinue
    Update-PathFromRegistry
    return Find-Python
}

function Install-VcRedist {
    Write-Host "Installing the Microsoft Visual C++ runtime that webcam tracking needs."
    Write-Host "Windows will ask for permission - please click Yes." -ForegroundColor Yellow
    $file = Join-Path $env:TEMP "vc_redist.x64.exe"
    Invoke-WebRequest $VcRedistUrl -OutFile $file -UseBasicParsing
    try {
        Start-Process -FilePath $file -ArgumentList "/install", "/passive", "/norestart" -Verb RunAs -Wait
    } catch {
        Write-Host "Skipped (permission was not given)."
    }
    Remove-Item $file -ErrorAction SilentlyContinue
}

if ($env:HEADMOUSE_SETUP_TEST) { return }   # tests load the functions only

try {
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  HeadMouse setup" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan

    Step 1 "Checking for Python"
    $python = Find-Python
    if (-not $python) { $python = Install-Python }
    if (-not $python) {
        throw ("Python could not be installed automatically. Install Python 3.13 from " +
               "https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH'), then run setup again.")
    }
    Write-Host "Using $python"

    Step 2 "Installing HeadMouse's parts (a few minutes the first time)"
    & $python -m pip install --upgrade --disable-pip-version-check --no-warn-script-location `
        -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Installing the parts failed. Check the internet connection and run setup again." }

    Step 3 "Getting the face model"
    & $python (Join-Path $Root "tools\get_face_model.py")

    Step 4 "Checking webcam tracking"
    & $python (Join-Path $Root "tools\check_webcam.py")
    if ($LASTEXITCODE -ne 0) {
        Install-VcRedist
        & $python (Join-Path $Root "tools\check_webcam.py")
    }

    Step 5 "Creating the HeadMouse icons"
    $pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
    & (Join-Path $PSScriptRoot "make_shortcut.ps1") -Target $pythonw `
        -Arguments ('"' + (Join-Path $Root "run_headmouse.pyw") + '"') -WorkingDirectory $Root

    Write-Host ""
    Write-Host "All done! HeadMouse is starting - use the HeadMouse icon on the desktop next time." -ForegroundColor Green
    if (-not $NoLaunch) {
        Start-Process -FilePath $pythonw -ArgumentList ('"' + (Join-Path $Root "run_headmouse.pyw") + '"') `
            -WorkingDirectory $Root
        Start-Sleep -Seconds 4
    }
    exit 0
} catch {
    Write-Host ""
    Write-Host "Setup could not finish: $_" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}
