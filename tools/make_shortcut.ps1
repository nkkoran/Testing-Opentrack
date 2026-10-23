# Creates "HeadMouse" shortcuts on the desktop and in the Start menu.
# Usage: make_shortcut.ps1 -Target <program> [-Arguments <text>] [-WorkingDirectory <folder>]
param(
    [Parameter(Mandatory = $true)][string]$Target,
    [string]$Arguments = "",
    [string]$WorkingDirectory = ""
)
$folder = Split-Path -Parent $PSScriptRoot
if (-not $WorkingDirectory) { $WorkingDirectory = Split-Path -Parent $Target }
$icon = Join-Path $folder "headmouse.ico"
if (-not (Test-Path -LiteralPath $icon)) { $icon = "$env:SystemRoot\System32\shell32.dll,43" }
$shell = New-Object -ComObject WScript.Shell
foreach ($place in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
    $link = $shell.CreateShortcut((Join-Path $place "HeadMouse.lnk"))
    $link.TargetPath = $Target
    $link.Arguments = $Arguments
    $link.WorkingDirectory = $WorkingDirectory
    $link.IconLocation = $icon
    $link.Description = "HeadMouse - head control for games"
    $link.Save()
}
Write-Host "Created HeadMouse icons on the desktop and in the Start menu."
