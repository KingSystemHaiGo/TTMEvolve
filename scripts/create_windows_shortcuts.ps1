# Create visible Windows shortcuts for TTMEvolve without exposing a console window.

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Shell = New-Object -ComObject WScript.Shell

function New-LauncherShortcut {
    param(
        [string]$Name,
        [string]$Target
    )
    $ShortcutPath = Join-Path $ProjectRoot "$Name.lnk"
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = Join-Path $env:SystemRoot "System32\wscript.exe"
    $Shortcut.Arguments = "`"$(Join-Path $ProjectRoot $Target)`""
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
    $Shortcut.Description = $Name
    $Shortcut.Save()
    Write-Host "[TTMEvolve] Created: $ShortcutPath"
}

New-LauncherShortcut -Name "TTMEvolve" -Target "TTMEvolve.vbs"
New-LauncherShortcut -Name "TTMEvolve Practice" -Target "TTMEvolve-Practice.vbs"
