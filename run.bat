@echo off
echo.
echo  MISSION CONTROL — Stat Tracker
echo  ================================
echo  [1] Desktop App  (original tkinter)
echo  [2] Web App      (Streamlit browser)
echo.
set /p choice="Choose 1 or 2: "

if "%choice%"=="1" goto desktop
if "%choice%"=="2" goto web
echo Invalid choice. Please enter 1 or 2.
pause
goto :eof

:desktop
py -3.11 -c "import anthropic" 2>nul || py -3.11 -m pip install anthropic --quiet
py -3.11 "%~dp0app.py"
goto :eof

:web
py -3.11 -c "import streamlit" 2>nul || py -3.11 -m pip install -r "%~dp0requirements.txt" --quiet
py -3.11 -m streamlit run "%~dp0streamlit_app.py"
goto :eof
