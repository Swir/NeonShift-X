@echo off
cd /d "%~dp0"
py -3 NeonShift_X.py
if errorlevel 1 pause
