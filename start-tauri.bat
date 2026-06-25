@echo off
REM =============================================================================
REM TTMEvolve 启动脚本 (Windows) — 优先内嵌环境
REM
REM 启动顺序：
REM   1. 检测内嵌 Python (./portable/python/python.exe)
REM   2. 退回 .venv/Scripts/python.exe
REM   3. 退回系统 PATH 上的 python
REM   4. 启动 Tauri 主程序 (TTMEvolve.exe)
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
echo [start-tauri] please install Python or run scripts\build-portable\build-all.bat
exit /b 1

:start_app

REM 内嵌 Node (供前端 dev server 使用)
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

:run_app

REM 启动 Tauri 主程序（开发模式使用 cargo-tauri；生产模式直接运行 exe）
if exist "src-tauri\target\release\ttmevolve.exe" (
    echo [start-tauri] starting production build
    "src-tauri\target\release\ttmevolve.exe" --python-exe "%PYTHON_EXE%"
) else if exist "src-tauri\target\debug\ttmevolve.exe" (
    echo [start-tauri] starting debug build
    "src-tauri\target\debug\ttmevolve.exe" --python-exe "%PYTHON_EXE%"
) else (
    echo [start-tauri] no built binary found; falling back to python main.py
    "%PYTHON_EXE%" main.py --embedded %*
)

endlocal