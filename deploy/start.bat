@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
:: SBS Archie — Запуск (start.bat)
:: Активирует venv, запускает admin_web (оркестратор),
:: admin_web сам запустит процессы из launch_config.json.
:: Включает watchdog: перезапуск admin_web при падении.
:: ============================================================

set "PROJECT_DIR=C:\SBS_Archie"
set "VENV_DIR=%PROJECT_DIR%\venv_name"
set "FRONTEND_DIR=%PROJECT_DIR%\admin_web\frontend"
set "FRONTEND_DIST_INDEX=%FRONTEND_DIR%\dist\index.html"
set "LOGS_DIR=%PROJECT_DIR%\logs"
set "ADMIN_WEB_LOG=%LOGS_DIR%\admin_web.log"
set "HEALTH_URL=http://localhost:8090/api/health"
set "ADMIN_WEB_HOST=0.0.0.0"
set "WATCHDOG_INTERVAL=30"
set "MAX_RESTART_ATTEMPTS=5"

:: Переход в директорию проекта
cd /d "%PROJECT_DIR%" || (
    echo [%date% %time%] ОШИБКА: Директория проекта не найдена: %PROJECT_DIR%
    pause
    exit /b 1
)

:: Создание папки логов
if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%"

:: Ротация лога admin_web (переименовываем старый)
if exist "%ADMIN_WEB_LOG%" (
    for /f "tokens=1-3 delims=/.- " %%a in ("%date%") do set "D=%%c-%%b-%%a"
    for /f "tokens=1-2 delims=:." %%a in ("%time: =0%") do set "T=%%a%%b"
    set "ROTATED_LOG=%LOGS_DIR%\admin_web_!D!_!T!.log"
    move "%ADMIN_WEB_LOG%" "!ROTATED_LOG!" >nul 2>&1
    echo [%date% %time%] Лог ротирован: !ROTATED_LOG!
)

:: Удаление логов старше 7 дней
forfiles /p "%LOGS_DIR%" /m "admin_web_*.log" /d -7 /c "cmd /c del @file" >nul 2>&1

:: Проверка наличия venv
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [%date% %time%] ОШИБКА: venv не найден: %VENV_DIR%
    echo Запустите setup.bat для первоначальной настройки.
    pause
    exit /b 1
)

:: Активация venv
call "%VENV_DIR%\Scripts\activate.bat"

:: Проверка React build (иначе API доступен, а UI отдаёт 404)
if not exist "%FRONTEND_DIST_INDEX%" (
    echo [%date% %time%] React build не найден, попытка сборки frontend...
    where npm >nul 2>&1
    if errorlevel 1 (
        echo [%date% %time%] ПРЕДУПРЕЖДЕНИЕ: npm не найден, UI может быть недоступен (только API).
    ) else (
        cd /d "%FRONTEND_DIR%"
        call npm install --silent 2>nul
        call npm run build
        if errorlevel 1 (
            echo [%date% %time%] ПРЕДУПРЕЖДЕНИЕ: сборка frontend не удалась, UI может быть недоступен.
        ) else (
            echo [%date% %time%] Frontend успешно собран.
        )
        cd /d "%PROJECT_DIR%"
    )
)

echo [%date% %time%] =========================================
echo [%date% %time%] SBS Archie — Запуск
echo [%date% %time%] Проект: %PROJECT_DIR%
echo [%date% %time%] Лог: %ADMIN_WEB_LOG%
echo [%date% %time%] =========================================

:: ---- Watchdog loop ----
set "RESTART_COUNT=0"

:watchdog_loop

if !RESTART_COUNT! GEQ %MAX_RESTART_ATTEMPTS% (
    echo [%date% %time%] КРИТИЧЕСКАЯ ОШИБКА: admin_web упал %MAX_RESTART_ATTEMPTS% раз подряд.
    echo [%date% %time%] Автоматический перезапуск остановлен.
    echo [%date% %time%] Проверьте лог: %ADMIN_WEB_LOG%
    pause
    exit /b 1
)

echo [%date% %time%] Запуск admin_web (попытка !RESTART_COUNT! из %MAX_RESTART_ATTEMPTS%)...

:: Запускаем admin_web в фоне через start /min
start /min "SBS_Archie_AdminWeb" cmd /c "cd /d %PROJECT_DIR% && call %VENV_DIR%\Scripts\activate.bat && set ADMIN_WEB_HOST=%ADMIN_WEB_HOST% && python -m admin_web >> %ADMIN_WEB_LOG% 2>&1"

:: Ждём 10 секунд для инициализации
echo [%date% %time%] Ожидание инициализации admin_web (10 сек)...
timeout /t 10 /nobreak >nul

:: Проверяем, что admin_web запустился
curl -s -o nul -w "%%{http_code}" "%HEALTH_URL%" | findstr "200" >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] ПРЕДУПРЕЖДЕНИЕ: admin_web не ответил на health check, ждём ещё 15 сек...
    timeout /t 15 /nobreak >nul
)

echo [%date% %time%] Watchdog активен. Интервал проверки: %WATCHDOG_INTERVAL% сек.

:health_check_loop
    timeout /t %WATCHDOG_INTERVAL% /nobreak >nul

    :: Проверяем health endpoint
    curl -s -o nul -w "%%{http_code}" "%HEALTH_URL%" | findstr "200" >nul 2>&1
    if errorlevel 1 (
        echo [%date% %time%] ПРЕДУПРЕЖДЕНИЕ: admin_web не отвечает!

        :: Двойная проверка
        timeout /t 5 /nobreak >nul
        curl -s -o nul -w "%%{http_code}" "%HEALTH_URL%" | findstr "200" >nul 2>&1
        if errorlevel 1 (
            echo [%date% %time%] admin_web подтверждённо недоступен. Перезапуск...

            :: Убиваем старый процесс
            taskkill /fi "WINDOWTITLE eq SBS_Archie_AdminWeb" /f >nul 2>&1
            timeout /t 3 /nobreak >nul

            set /a RESTART_COUNT+=1
            goto :watchdog_loop
        ) else (
            echo [%date% %time%] admin_web восстановился ^(ложная тревога^).
        )
    )
goto :health_check_loop
