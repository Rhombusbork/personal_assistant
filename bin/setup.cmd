@echo off
rem First-time setup on Windows: bin\setup.cmd   (safe to run again)
setlocal
set PYTHONUTF8=1
cd /d "%~dp0.."
where py >nul 2>nul
if %errorlevel% equ 0 (py -3 scripts\setup.py) else (python scripts\setup.py)
exit /b %errorlevel%
