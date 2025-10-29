@echo off
cd /d %~dp0
call .venv\Scripts\activate
python app2.py
pause
