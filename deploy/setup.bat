@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
:: SBS Archie — Первоначальная настройка (setup.bat)
:: Проверяет окружение, создаёт venv, устанавливает
:: зависимости, собирает frontend, создаёт структуру папок.
:: ============================================================

set "PROJECT_DIR=C:\SBS_Archie"
set "VENV_DIR=%PROJECT_DIR%\venv_name"
set "FRONTEND_DIR=%PROJECT_DIR%\admin_web\frontend"

echo =========================================
echo  SBS Archie — Первоначальная настройка
echo =========================================
echo.

:: Переход в директорию проекта
cd /d "%PROJECT_DIR%" || (
    echo [ОШИБКА] Директория проекта не найдена: %PROJECT_DIR%
    echo Сначала клонируйте репозиторий:
    echo   git clone ^<repository-url^> %PROJECT_DIR%
    pause
    exit /b 1
)

:: ---- Проверка предварительных условий ----
echo [1/7] Проверка предварительных условий...

:: Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден. Установите Python 3.10+
    echo   https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo   Python: %PY_VER%

:: Git
where git >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Git не найден. Установите Git для Windows.
    echo   https://git-scm.com/download/win
    pause
    exit /b 1
)
for /f "tokens=3 delims= " %%v in ('git --version') do set "GIT_VER=%%v"
echo   Git: %GIT_VER%

:: Node.js
where node >nul 2>&1
if errorlevel 1 (
    echo [ПРЕДУПРЕЖДЕНИЕ] Node.js не найден. Frontend не будет собран.
    echo   https://nodejs.org/
    set "HAS_NODE=0"
) else (
    for /f "tokens=1 delims= " %%v in ('node --version') do set "NODE_VER=%%v"
    echo   Node.js: !NODE_VER!
    set "HAS_NODE=1"
)

:: curl
where curl >nul 2>&1
if errorlevel 1 (
    echo [ПРЕДУПРЕЖДЕНИЕ] curl не найден. Watchdog не будет работать.
    echo   curl обычно есть в Windows 10+.
) else (
    echo   curl: доступен
)

echo.

:: ---- Создание venv ----
echo [2/7] Создание виртуального окружения...
if exist "%VENV_DIR%\Scripts\activate.bat" (
    echo   venv уже существует: %VENV_DIR%
) else (
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать venv.
        pause
        exit /b 1
    )
    echo   venv создан: %VENV_DIR%
)
echo.

:: ---- Установка Python-зависимостей ----
echo [3/7] Установка Python-зависимостей...
call "%VENV_DIR%\Scripts\activate.bat"
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ОШИБКА] pip install не удался.
    pause
    exit /b 1
)
echo   Python-зависимости установлены.
echo.

:: ---- Сборка frontend ----
echo [4/7] Сборка frontend...
if "%HAS_NODE%"=="0" (
    echo   [ПРОПУСК] Node.js не установлен.
) else (
    cd /d "%FRONTEND_DIR%"
    call npm install --silent 2>nul
    call npm run build
    if errorlevel 1 (
        echo [ОШИБКА] Сборка frontend не удалась.
        cd /d "%PROJECT_DIR%"
        pause
        exit /b 1
    )
    cd /d "%PROJECT_DIR%"
    echo   Frontend собран.
)
echo.

:: ---- Создание структуры папок ----
echo [5/7] Создание структуры папок...
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"
if not exist "%PROJECT_DIR%\deploy\backups" mkdir "%PROJECT_DIR%\deploy\backups"
if not exist "%PROJECT_DIR%\data\group_knowledge" mkdir "%PROJECT_DIR%\data\group_knowledge"
if not exist "%PROJECT_DIR%\data\qdrant" mkdir "%PROJECT_DIR%\data\qdrant"
echo   Папки созданы.
echo.

:: ---- Конфигурация ----
echo [6/7] Проверка конфигурации...
if not exist "%PROJECT_DIR%\config\.env" (
    if exist "%PROJECT_DIR%\config\.env.example" (
        copy "%PROJECT_DIR%\config\.env.example" "%PROJECT_DIR%\config\.env" >nul
        echo   .env создан из .env.example — ОТРЕДАКТИРУЙТЕ ЕГО!
    ) else (
        echo   [ПРЕДУПРЕЖДЕНИЕ] .env.example не найден. Создайте config\.env вручную.
    )
) else (
    echo   config\.env уже существует.
)
echo.

:: ---- Готово ----
echo [7/7] Настройка завершена!
echo.
echo =========================================
echo  Следующие шаги:
echo =========================================
echo.
echo  1. Отредактируйте config\.env с вашими настройками
echo     (API ключи, подключение к БД, токены Telegram)
echo.
echo  2. Настройте базу данных MySQL:
echo     mysql -u root -p ^< schema.sql
echo     Затем выполните скрипты из папки sql\
echo.
echo  3. Настройте deploy\launch_config.json
echo     (какие процессы запускать автоматически)
echo.
echo  4. Настройте автозапуск в Task Scheduler:
echo     deploy\task_scheduler_setup.bat
echo.
echo  5. Запустите вручную для проверки:
echo     deploy\start.bat
echo.
echo =========================================
pause
