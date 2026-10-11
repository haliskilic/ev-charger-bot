@echo off
rem Starts ev-charger-bot on Windows and appends its output to data\bot.log (rotated at 10 MB).
rem Use this file as the "Program/script" of the Task Scheduler task, or double-click it for a manual run.
cd /d "%~dp0.."
if not exist data mkdir data
for %%F in ("data\bot.log") do if %%~zF GTR 10485760 (
    if exist "data\bot.log.1" del "data\bot.log.1"
    ren "data\bot.log" "bot.log.1"
)
echo [%date% %time%] starting ev-charger-bot >> data\bot.log
venv\Scripts\python.exe -m evsarj.main >> data\bot.log 2>&1
