@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

REM Защита от самоперезаписи: update.bat может обновить сам себя через git reset.
REM Запускаем основную логику из временной копии, чтобы избежать ошибок парсинга.
if /i "%~1" NEQ "__RUNNER__" (
    set "RUNNER=%TEMP%\sbs_archie_update_runner.bat"
    copy "%~f0" "!RUNNER!" >nul 2>&1
    if errorlevel 1 (
        echo [%date% %time%] ОШИБКА: не удалось создать временную копию update.bat
        pause
        exit /b 1
    )
    call "!RUNNER!" __RUNNER__
    set "RC=%ERRORLEVEL%"
    del "!RUNNER!" >nul 2>&1
    exit /b %RC%
)
shift

REM ============================================================
REM SBS Archie — Обновление (update.bat)
REM Останавливает бота, обновляет из GitHub, пересобирает
REM frontend, обновляет зависимости и предлагает запуск.
REM ============================================================

set "PROJECT_DIR=C:\SBS_Archie"
set "VENV_DIR=%PROJECT_DIR%\venv_name"
set "BACKUP_DIR=%PROJECT_DIR%\deploy\backups"
set "FRONTEND_DIR=%PROJECT_DIR%\admin_web\frontend"

REM Переход в директорию проекта
cd /d "%PROJECT_DIR%" || (
    echo [%date% %time%] ОШИБКА: Директория проекта не найдена: %PROJECT_DIR%
    pause
    exit /b 1
)

echo [%date% %time%] =========================================
echo [%date% %time%] SBS Archie — Обновление
echo [%date% %time%] =========================================

REM ---- Шаг 1: Остановка ----
echo.
echo [%date% %time%] [1/6] Остановка текущих процессов...
call "%PROJECT_DIR%\deploy\stop.bat"
timeout /t 3 /nobreak >nul

REM ---- Шаг 2: Бэкап конфигурации ----
echo.
echo [%date% %time%] [2/6] Резервное копирование конфигурации...

REM Создаём папку бэкапов с датой
for /f "tokens=1-3 delims=/.- " %%a in ("%date%") do set "D=%%c-%%b-%%a"
for /f "tokens=1-2 delims=:." %%a in ("%time: =0%") do set "T=%%a%%b"
set "BACKUP_SUBDIR=%BACKUP_DIR%\%D%_%T%"
mkdir "%BACKUP_SUBDIR%" >nul 2>&1

if exist "%PROJECT_DIR%\config\.env" (
    copy "%PROJECT_DIR%\config\.env" "%BACKUP_SUBDIR%\.env" >nul
    echo [%date% %time%]   .env скопирован
)
if exist "%PROJECT_DIR%\deploy\launch_config.json" (
    copy "%PROJECT_DIR%\deploy\launch_config.json" "%BACKUP_SUBDIR%\launch_config.json" >nul
    echo [%date% %time%]   launch_config.json скопирован
)
if exist "%PROJECT_DIR%\config\gk_groups.json" (
    copy "%PROJECT_DIR%\config\gk_groups.json" "%BACKUP_SUBDIR%\gk_groups.json" >nul
    echo [%date% %time%]   gk_groups.json скопирован
)
if exist "%PROJECT_DIR%\config\helper_groups.json" (
    copy "%PROJECT_DIR%\config\helper_groups.json" "%BACKUP_SUBDIR%\helper_groups.json" >nul
    echo [%date% %time%]   helper_groups.json скопирован
)

echo [%date% %time%]   Бэкап: %BACKUP_SUBDIR%

REM Удаление бэкапов старше 30 дней
forfiles /p "%BACKUP_DIR%" /d -30 /c "cmd /c if @isdir==TRUE rmdir /s /q @path" >nul 2>&1

REM ---- Шаг 3: Сохранение текущей версии ----
echo.
echo [%date% %time%] [3/6] Обновление из GitHub (main)...

if exist "%PROJECT_DIR%\VERSION" (
    set /p OLD_VERSION=<"%PROJECT_DIR%\VERSION"
) else (
    set "OLD_VERSION=неизвестно"
)

REM Git: принудительная синхронизация с origin/main
git fetch origin main
if errorlevel 1 (
    echo [%date% %time%] ОШИБКА: git fetch не удался. Проверьте сетевое подключение.
    pause
    exit /b 1
)

git checkout main >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] Ветка main не найдена локально, создаём tracking-ветку...
    git checkout -b main --track origin/main
    if errorlevel 1 (
        echo [%date% %time%] ОШИБКА: не удалось создать локальную ветку main.
        pause
        exit /b 1
    )
)

git reset --hard origin/main
if errorlevel 1 (
    echo [%date% %time%] ОШИБКА: не удалось синхронизироваться с origin/main.
    pause
    exit /b 1
)

if exist "%PROJECT_DIR%\VERSION" (
    set /p NEW_VERSION=<"%PROJECT_DIR%\VERSION"
) else (
    set "NEW_VERSION=неизвестно"
)

echo [%date% %time%]   Обновлено: !OLD_VERSION! -^> !NEW_VERSION!

REM ---- Шаг 4: Обновление зависимостей Python ----
echo.
echo [%date% %time%] [4/6] Обновление Python-зависимостей...
call "%VENV_DIR%\Scripts\activate.bat"
set "REQ_NO_TORCH=%TEMP%\sbs_archie_requirements_no_torch.txt"
python -c "from pathlib import Path; src=Path('requirements.txt'); dst=Path(r'%REQ_NO_TORCH%'); lines=src.read_text(encoding='utf-8').splitlines(); skip=('torch','torchvision','torchaudio'); filtered=[ln for ln in lines if not ln.strip().lower().startswith(skip)]; dst.write_text(('\n'.join(filtered)+'\n') if filtered else '', encoding='utf-8')"
if errorlevel 1 (
    echo [%date% %time%] ОШИБКА: не удалось подготовить requirements без torch-пакетов.
    pause
    exit /b 1
)

pip install -r "%REQ_NO_TORCH%" --quiet
if errorlevel 1 (
    echo [%date% %time%] ПРЕДУПРЕЖДЕНИЕ: pip install завершился с ошибкой.
) else (
    echo [%date% %time%]   Python-зависимости обновлены.

    REM Устанавливаем torch-стек отдельно, чтобы исключить конфликты версий и двойную установку.
    set "TORCH_SPEC=torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0"
    set "TORCH_INDEX="
    set "TORCH_MODE=cpu"

    where nvidia-smi >nul 2>&1
    if not errorlevel 1 (
        nvidia-smi >nul 2>&1
        if not errorlevel 1 (
            set "TORCH_SPEC=torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124"
            set "TORCH_INDEX=--index-url https://download.pytorch.org/whl/cu124"
            set "TORCH_MODE=gpu"
            echo [%date% %time%]   NVIDIA GPU обнаружен: будет установлена CUDA-сборка torch (cu124).
        ) else (
            echo [%date% %time%]   nvidia-smi недоступен, будет установлена CPU-сборка torch.
        )
    ) else (
        echo [%date% %time%]   NVIDIA GPU не обнаружен: будет установлена CPU-сборка torch.
    )

    echo [%date% %time%]   Установка torch-стека: !TORCH_SPEC!
    python -m pip uninstall -y torch torchvision torchaudio >nul 2>&1
    python -m pip install !TORCH_SPEC! !TORCH_INDEX!
    if errorlevel 1 (
        echo [%date% %time%] ПРЕДУПРЕЖДЕНИЕ: установка torch-стека не удалась.
    ) else (
        for /f "tokens=*" %%v in ('python -c "import torch; print(int(torch.cuda.is_available()))"') do set "TORCH_CUDA_READY=%%v"
        if "!TORCH_CUDA_READY!"=="1" (
            echo [%date% %time%]   torch установлен и CUDA доступна.
        ) else (
            echo [%date% %time%]   torch установлен (CPU режим).
        )
    )
)

if exist "%REQ_NO_TORCH%" del "%REQ_NO_TORCH%" >nul 2>&1

REM ---- Шаг 5: Пересборка frontend ----
echo.
echo [%date% %time%] [5/6] Пересборка frontend...

where npm >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] ПРЕДУПРЕЖДЕНИЕ: npm не найден. Frontend не будет пересобран.
    echo [%date% %time%] Установите Node.js: https://nodejs.org/
    goto :skip_frontend
)

cd /d "%FRONTEND_DIR%"
call npm install --silent 2>nul
call npm run build
if errorlevel 1 (
    echo [%date% %time%] ОШИБКА: Сборка frontend не удалась!
    cd /d "%PROJECT_DIR%"
    pause
    exit /b 1
)
cd /d "%PROJECT_DIR%"
echo [%date% %time%]   Frontend успешно пересобран.


:skip_frontend

REM ---- Шаг 6: Итог ----
echo.
echo [%date% %time%] [6/6] Обновление завершено.
echo [%date% %time%] =========================================
echo [%date% %time%]   Версия: !NEW_VERSION!
echo [%date% %time%]   Бэкап:  %BACKUP_SUBDIR%
echo [%date% %time%] =========================================
echo.

set /p START_NOW="Запустить SBS Archie? (y/n): "
if /i "%START_NOW%"=="y" (
    echo [%date% %time%] Запуск...
    call "%PROJECT_DIR%\deploy\start.bat"
) else (
    echo [%date% %time%] Для запуска выполните: deploy\start.bat
)
