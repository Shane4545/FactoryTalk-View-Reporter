@echo off
title Build Ops Reporter SCADA kit
cd /d "%~dp0"
echo Building OpsReporter.exe + zip for SCADA PC...
echo.
"C:\Users\sgordon\AppData\Local\Programs\Python\Python311\python.exe" package_scada_kit.py
if errorlevel 1 (
  echo BUILD FAILED
  pause
  exit /b 1
)
echo.
explorer "releases"
pause
