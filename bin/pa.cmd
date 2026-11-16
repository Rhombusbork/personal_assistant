@echo off
rem Assistant command on Windows: bin\pa.cmd <command>   (bin\pa.cmd -h for help)
rem Exit code 75 means "code changed, start again" (the engine restarts itself with new code).
setlocal
set PYTHONUTF8=1
set PA_LOOP=1
cd /d "%~dp0.."
:again
".venv\Scripts\python.exe" -m pa %*
if %errorlevel% equ 75 goto again
exit /b %errorlevel%
