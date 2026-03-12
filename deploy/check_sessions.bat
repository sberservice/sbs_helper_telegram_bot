@echo off
chcp 65001 >nul 2>&1
setlocal

REM Проверка Telethon-сессий для deploy
set "PROJECT_DIR=C:\SBS_Archie"
set "PYTHON_EXE=%PROJECT_DIR%\venv_name\Scripts\python.exe"

cd /d "%PROJECT_DIR%" || exit /b 1

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" "%PROJECT_DIR%\deploy\check_telethon_sessions.py" --project-dir "%PROJECT_DIR%"
) else (
    python "%PROJECT_DIR%\deploy\check_telethon_sessions.py" --project-dir "%PROJECT_DIR%"
)

exit /b %ERRORLEVEL%
