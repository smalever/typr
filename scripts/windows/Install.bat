@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1" %*
set "typr_exit=%errorlevel%"
if "%~1"=="" pause
exit /b %typr_exit%
