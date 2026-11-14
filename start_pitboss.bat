@echo off
title Pit Boss - leave this window open
cd /d "%~dp0"
echo Checking for updates to the Discord library...
py -m pip install --quiet --upgrade -r requirements.txt
:loop
py pitboss_bot.py
echo.
echo Pit Boss stopped. Restarting in 30 seconds... (close this window to stop it for good)
timeout /t 30 /nobreak >nul
goto loop
