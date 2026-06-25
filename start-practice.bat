@echo off
chcp 65001 >nul

echo [TTMEvolve Practice] Starting one-click Maker practice setup...

powershell -Command "Get-Command powershell" >nul 2>&1
if errorlevel 1 (
    echo [TTMEvolve Practice] Error: PowerShell not found.
    pause
    exit /b 1
)

powershell -ExecutionPolicy Bypass -File "%~dp0start-practice.ps1" %*
set EXITCODE=%errorlevel%

if %EXITCODE% neq 0 (
    echo [TTMEvolve Practice] Failed with exit code: %EXITCODE%
    pause
)

exit /b %EXITCODE%
