@echo off
REM =============================================================================
REM TTMEvolve launcher (Windows) - prefers portable runtime
REM
REM v1.0.0 stable:
REM   - vendor Python first, then .venv, then system Python
REM   - GUI / CLI / headless modes
REM   - source checkout GUI fallback builds frontend and release Tauri
REM   - friendly error messages
REM =============================================================================

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PYTHON_EXE="

REM 1. Embedded Python (vendor)
if exist "vendor\python\python.exe" (
    set "PYTHON_EXE=%CD%\vendor\python\python.exe"
    echo [start-tauri] using embedded python: !PYTHON_EXE!
    goto :python_found
)

REM 2. .venv virtual environment
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
    echo [start-tauri] using venv python: !PYTHON_EXE!
    goto :python_found
)

REM 3. System Python
where python >nul 2>nul
if %errorlevel%==0 (
    for /f "delims=" %%i in ('where python') do (
        set "PYTHON_EXE=%%i"
        echo [start-tauri] using system python: !PYTHON_EXE!
        goto :python_found
    )
)

echo [start-tauri] ERROR: no python found (vendor, .venv, or system)
echo [start-tauri] run scripts\build_embedded.py --mode full --skip-model to prepare vendor runtime
exit /b 1

:python_found

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

set "TTM_PYTHON_EXE=!PYTHON_EXE!"
set "TTMEVOLVE_ROOT=%CD%"

if "!MODE!"=="gui" goto :run_gui
goto :run_backend

:run_gui
if exist "src-tauri\target\release\ttmevolve.exe" (
    start "TTMEvolve" "%CD%\src-tauri\target\release\ttmevolve.exe" %*
    exit /b 0
)

if /i "!TTMEVOLVE_ALLOW_DEBUG_GUI!"=="1" if exist "src-tauri\target\debug\ttmevolve.exe" (
    start "TTMEvolve" "%CD%\src-tauri\target\debug\ttmevolve.exe" %*
    exit /b 0
)

where cargo >nul 2>nul
if errorlevel 1 (
    echo [start-tauri] ERROR: no built Tauri binary found and Cargo is unavailable
    echo [start-tauri] install Rust/Cargo or use a packaged TTMEvolve build
    exit /b 1
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
    echo [start-tauri] ERROR: npm.cmd not found; cannot build frontend for Tauri
    echo [start-tauri] please install Node.js or run scripts\build_embedded.py --mode full --skip-model
    exit /b 1
)

echo [start-tauri] no release binary; building frontend for Tauri
npm.cmd --prefix frontend run build
if errorlevel 1 exit /b %errorlevel%

echo [start-tauri] building Tauri release
cargo build --release --manifest-path src-tauri\Cargo.toml
if errorlevel 1 exit /b %errorlevel%

start "TTMEvolve" "%CD%\src-tauri\target\release\ttmevolve.exe" %*
exit /b 0

:run_backend
"!PYTHON_EXE!" main.py --embedded %*
exit /b %errorlevel%
