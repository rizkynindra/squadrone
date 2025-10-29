@echo off
cd /d %~dp0
call .venv\Scripts\activate
waitress-serve --listen=0.0.0.0:5000 app2:app
pause
