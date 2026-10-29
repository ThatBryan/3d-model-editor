@echo off
rem Double-click to start the 3D model editor. Options pass through, e.g. start.cmd -Mock
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 pause
