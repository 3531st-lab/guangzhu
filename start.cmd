@echo off
setlocal
set PYTHONUTF8=1
"%~dp0.venv\Scripts\python.exe" -m guangzhu.selfcheck
if errorlevel 1 exit /b %errorlevel%
"%~dp0.venv\Scripts\python.exe" "%~dp0desktop\app.py"
exit /b %errorlevel%
