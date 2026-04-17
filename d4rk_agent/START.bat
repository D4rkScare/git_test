@echo off
title SIRIAN AGENT
color 0A
echo.
echo  ========================================
echo   SIRIAN AGENT - Starting...
echo  ========================================
echo.
echo  [1] Installing packages...
py -3.11 -m pip install python-telegram-bot==20.7 -q 2>nul

echo  [2] Starting main server...
start "SIRIAN MAIN" cmd /k "cd /d %~dp0 && py -3.11 main.py"

timeout /t 3 /nobreak > nul

echo  [3] Starting Telegram bot...
start "SIRIAN TELEGRAM" cmd /k "cd /d %~dp0 && py -3.11 telegram_bot.py"

timeout /t 2 /nobreak > nul

echo  [4] Opening browser...
start "" http://localhost:7865

echo.
echo  All systems started!
echo  Browser: http://localhost:7865
echo  Close each window to stop.
echo.
pause
