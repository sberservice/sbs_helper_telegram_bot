@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
:: SBS Archie — Остановка (stop.bat)
:: Останавливает все процессы через admin_web API,
:: затем завершает сам admin_web.
:: ============================================================

set "PROJECT_DIR=C:\SBS_Archie"
set "SHUTDOWN_URL=http://localhost:8090/api/process-manager/shutdown"
set "HEALTH_URL=http://localhost:8090/api/health"

echo [%date% %time%] =========================================
echo [%date% %time%] SBS Archie — Остановка
echo [%date% %time%] =========================================

:: Проверяем, доступен ли admin_web
curl -s -o nul -w "%%{http_code}" "%HEALTH_URL%" | findstr "200" >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] admin_web не запущен или не отвечает.
    echo [%date% %time%] Попытка завершить процессы напрямую...
    goto :force_kill
)

:: Отправляем команду на graceful shutdown
echo [%date% %time%] Отправка команды на остановку через API...
curl -s -X POST "%SHUTDOWN_URL%" -o nul 2>&1

:: Ждём завершения (макс 15 секунд)
set "WAIT_COUNT=0"
:wait_shutdown
    timeout /t 2 /nobreak >nul
    set /a WAIT_COUNT+=1

    curl -s -o nul -w "%%{http_code}" "%HEALTH_URL%" | findstr "200" >nul 2>&1
    if errorlevel 1 (
        echo [%date% %time%] admin_web завершён успешно.
        goto :kill_watchdog
    )

    if !WAIT_COUNT! GEQ 7 (
        echo [%date% %time%] admin_web не завершился за 15 секунд. Принудительное завершение...
        goto :force_kill
    )

    echo [%date% %time%] Ожидание завершения... (!WAIT_COUNT!/7)
goto :wait_shutdown

:force_kill
echo [%date% %time%] Принудительное завершение процессов...

:: Убиваем процессы Python, связанные с проектом
taskkill /fi "WINDOWTITLE eq SBS_Archie_AdminWeb" /f >nul 2>&1

:: Пауза для освобождения ресурсов
timeout /t 2 /nobreak >nul

:kill_watchdog
:: Завершаем окно watchdog (start.bat)
taskkill /fi "WINDOWTITLE eq SBS_Archie_Watchdog" /f >nul 2>&1

echo [%date% %time%] =========================================
echo [%date% %time%] Все процессы остановлены.
echo [%date% %time%] =========================================
