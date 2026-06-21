@echo off
REM Build the all-in-one StarRuptureTimer.exe (timer + recipe search, no console).
REM Run srextract.exe FIRST to generate recipes.json + icons from your own game copy.
REM (Empty placeholders are created below so the build never fails; recipes.json is
REM also read externally next to the exe, so you can drop in updated data anytime.)

if not exist icons mkdir icons
if not exist recipes.json echo {"recipes":[]}>recipes.json
if not exist icons.json echo {}>icons.json

python -m PyInstaller --onefile --noconsole --name StarRuptureTimer ^
  --add-data "recipes.json;." ^
  --add-data "icons.json;." ^
  --add-data "icons;icons" ^
  --hidden-import "PIL._tkinter_finder" overlay.py

echo.
echo Done. Your exe is at:  dist\StarRuptureTimer.exe
echo (Keep recipes.json next to the exe to override the bundled data.)
pause
