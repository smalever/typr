@echo off
setlocal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1" -Uninstall %*
set "typr_exit=%errorlevel%"
if "%~1"=="" pause
exit /b %typr_exit%
