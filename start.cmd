@echo off
setlocal
set PYTHONUTF8=1
"%~dp0.venv\Scripts\python.exe" -m guangzhu.selfcheck
exit /b %errorlevel%
