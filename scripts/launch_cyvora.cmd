@echo off
REM One-click entry for CYVORA. This does not register a scheduled task or a service.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_cyvora.ps1" %*
exit /b %ERRORLEVEL%
