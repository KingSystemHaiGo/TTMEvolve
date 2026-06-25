@echo off
chcp 65001 >nul
echo [TTMEvolve] 正在启动...

powershell -Command "Get-Command powershell" >nul 2>&1
if errorlevel 1 (
    echo [TTMEvolve] 错误: 未找到 PowerShell。
    pause
    exit /b 1
)

powershell -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set EXITCODE=%errorlevel%
if %EXITCODE% neq 0 (
    echo [TTMEvolve] 启动过程异常，退出码: %EXITCODE%
    pause
)
