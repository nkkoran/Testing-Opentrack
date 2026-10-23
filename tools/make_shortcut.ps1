# Creates a "HeadMouse" shortcut on the desktop.
# Usage: make_shortcut.ps1 [-Exe <path to HeadMouse.exe>]
param([string]$Exe = "")
$folder = Split-Path -Parent $PSScriptRoot
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "HeadMouse.lnk"))
if ($Exe -ne "") {
    $link.TargetPath = $Exe
    $link.WorkingDirectory = Split-Path -Parent $Exe
} else {
    $pyw = (Get-Command pyw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pyw) { Write-Host "pyw.exe (Python launcher) not found - shortcut not created."; exit 1 }
    $link.TargetPath = $pyw
    $link.Arguments = "-3 `"$folder\run_headmouse.pyw`""
    $link.WorkingDirectory = $folder
    $link.IconLocation = "$env:SystemRoot\System32\shell32.dll,43"
}
$link.Description = "HeadMouse - head control for games"
$link.Save()
Write-Host "Created desktop shortcut: HeadMouse"
