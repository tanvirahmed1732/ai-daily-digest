@echo off
cd /d "%~dp0"
py -3 ai_digest.py >> bat_run.log 2>&1
