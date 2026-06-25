@echo off
REM =============================================================================
REM TTMEvolve 启动脚本 (Windows) — 优先内嵌环境
REM
REM v0.9.0 增强：
REM   - 优先 portable 内嵌环境
REM   - GUI / CLI / Headless 模式选择
REM   - 友好的错误信息
REM =============================================================================

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PYTHON_EXE="

REM 1. 内嵌 Python (portable)
if exist "portable\python\python.exe" (
    set "PYTHON_EXE=%CD%\portable\python\python.exe"
    echo [start-tauri] using embedded python: !PYTHON_EXE!
    goto :start_app
)

REM 2. .venv 虚拟环境
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
    echo [start-tauri] using venv python: !PYTHON_EXE!
    goto :start_app
)

REM 3. 系统 Python
where python >nul 2>nul
if %errorlevel%==0 (
    for /f "delims=" %%i in ('where python') do (
        set "PYTHON_EXE=%%i"
        echo [start-tauri] using system python: !PYTHON_EXE!
        goto :start_app
    )
)

echo [start-tauri] ERROR: no python found (portable, venv, or system)
echo [start-tauri] please install Python or run scripts\build-portable\build_all.bat
exit /b 1

:start_app

REM 内嵌 Node
set "NODE_EXE="
if exist "portable\node\node.exe" (
    set "NODE_EXE=%CD%\portable\node\node.exe"
) else (
    where node >nul 2>nul
    if %errorlevel%==0 (
        for /f "delims=" %%i in ('where node') do (
            set "NODE_EXE=%%i"
            goto :run_app
        )
    )
)

REM 模式选择
set "MODE=gui"
if "%1"=="--cli" (
    set "MODE=cli"
    shift
)
if "%1"=="--headless" (
    set "MODE=headless"
    shift
)
echo [start-tauri] mode: !MODE!

:run_app

if "!MODE!"=="gui" (
    REM 启动 Tauri 主程序
    if exist "src-tauri\target\release\ttmevolve.exe" (
        echo [start-tauri] starting production build
        "src-tauri\target\release\ttmevolve.exe" --python-exe "!PYTHON_EXE!"
    ) else if exist "src-tauri\target\debug\ttmevolve.exe" (
        echo [start-tauri] starting debug build
        "src-tauri\target\debug\ttmevolve.exe" --python-exe "!PYTHON_EXE!"
    ) else (
        echo [start-tauri] no built binary; falling back to python main.py
        "!PYTHON_EXE!" main.py --embedded %*
    )
) else (
    REM CLI / headless 模式：直接调用 Python
    "!PYTHON_EXE!" main.py --embedded %*
)

endlocal