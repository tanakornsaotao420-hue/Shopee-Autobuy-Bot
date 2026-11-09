@echo off
cd /d "%~dp0"
py -3 app.py
if errorlevel 1 (
  echo Please install Python 3 with Tcl/Tk, then run this file again.
  pause
)
