@echo off
REM Build MyPerfumery.exe (single-file Windows desktop app).
REM Requires: Python 3.11+, pip, and an internet connection for the first run.

setlocal
cd /d "%~dp0"

echo [1/3] Installing build dependencies...
python -m pip install --upgrade pip || goto :err
python -m pip install flask pywebview pyinstaller || goto :err

echo [2/3] Cleaning previous build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist MyPerfumery.spec del /q MyPerfumery.spec

echo [3/3] Running PyInstaller...
python -m PyInstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name MyPerfumery ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "data;data" ^
  --hidden-import=webview.platforms.edgechromium ^
  launcher.py || goto :err

echo.
echo Done. Output: dist\MyPerfumery.exe
goto :eof

:err
echo.
echo BUILD FAILED.
exit /b 1
