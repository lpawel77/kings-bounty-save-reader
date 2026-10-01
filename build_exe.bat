@echo off
rem Buduje dist\KB czytnik zapisu.exe - jeden plik, bez okna konsoli.
rem Wymaga: pip install pyinstaller pillow openpyxl
rem Przed budowaniem zamknij uruchomiony "KB czytnik zapisu.exe" (Windows blokuje nadpisanie).
cd /d "%~dp0"
tasklist /fi "imagename eq KB czytnik zapisu.exe" | find /i "KB czytnik zapisu.exe" >nul && (
  echo Zamknij najpierw uruchomiony "KB czytnik zapisu.exe".
  pause
  exit /b 1
)
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "KB czytnik zapisu" --icon kb_icon.ico --add-data "kb_icon.ico;." ^
  --exclude-module numpy --exclude-module pandas --exclude-module matplotlib --exclude-module scipy ^
  kb_app.py
echo.
echo Gotowe: dist\KB czytnik zapisu.exe
