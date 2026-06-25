@echo off
chcp 65001 >nul
REM TTMEvolve embedded launcher: uses vendor/python/node/git if present.
REM Run scripts/build_embedded.py first to populate vendor/.
powershell -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
