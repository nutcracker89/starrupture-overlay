@echo off
REM Build the all-in-one StarRuptureTimer.exe (timer + recipe search, no console).
REM recipes.json is bundled as a default AND read externally (next to the exe) if
REM present, so you can drop in updated/extracted recipe data without rebuilding.

python -m PyInstaller --onefile --noconsole --name StarRuptureTimer ^
  --add-data "recipes.json;." ^
  --add-data "icons.json;." ^
  --add-data "icons;icons" ^
  --hidden-import "PIL._tkinter_finder" overlay.py

echo.
echo Done. Your exe is at:  dist\StarRuptureTimer.exe
echo (Keep recipes.json next to the exe to override the bundled data.)
pause
