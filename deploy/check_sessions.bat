@echo off
chcp 65001 >nul 2>&1
setlocal

REM Проверка Telethon-сессий для deploy.
REM По умолчанию запускается в режиме "проверка + помощь в создании сессий".
REM Флаг --non-interactive: только проверка без диалога.

set "PROJECT_DIR=C:\SBS_Archie"
set "PYTHON_EXE=%PROJECT_DIR%\venv_name\Scripts\python.exe"
set "NON_INTERACTIVE=0"

if /i "%~1"=="--non-interactive" set "NON_INTERACTIVE=1"

cd /d "%PROJECT_DIR%" || exit /b 1

if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

:run_check
"%PYTHON_EXE%" "%PROJECT_DIR%\deploy\check_telethon_sessions.py" --project-dir "%PROJECT_DIR%"
set "RC=%ERRORLEVEL%"

if "%RC%"=="2" (
    if "%NON_INTERACTIVE%"=="1" exit /b 2

    echo.
    echo ========================================================
    echo Telethon sessions missing. Помощь по созданию сессий:
    echo ========================================================
    echo 1. Создать session для GK Collector
    echo    ^(%PYTHON_EXE% scripts\gk_collector.py --manage-groups^)
    echo 2. Создать session для The Helper
    echo    ^(%PYTHON_EXE% scripts\the_helper.py --manage-groups^)
    echo 3. Создать обе сессии по очереди
    echo 0. Выйти без создания
    echo.

    set /p SESSION_CHOICE="Выберите действие (0/1/2/3): "

    if "%SESSION_CHOICE%"=="1" (
        "%PYTHON_EXE%" scripts\gk_collector.py --manage-groups
        goto :run_check
    )
    if "%SESSION_CHOICE%"=="2" (
        "%PYTHON_EXE%" scripts\the_helper.py --manage-groups
        goto :run_check
    )
    if "%SESSION_CHOICE%"=="3" (
        "%PYTHON_EXE%" scripts\gk_collector.py --manage-groups
        "%PYTHON_EXE%" scripts\the_helper.py --manage-groups
        goto :run_check
    )

    exit /b 2
)

exit /b %RC%
