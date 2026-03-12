@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
:: SBS Archie — Настройка Task Scheduler (task_scheduler_setup.bat)
:: Создаёт задачу Windows для автозапуска при загрузке
:: с задержкой 2 минуты (ожидание БД и сети).
:: Запускать от имени администратора!
:: ============================================================

set "PROJECT_DIR=C:\SBS_Archie"
set "TASK_NAME=SBS_Archie"
set "START_SCRIPT=%PROJECT_DIR%\deploy\start.bat"
set "DELAY=0002:00"

echo =========================================
echo  SBS Archie — Настройка Task Scheduler
echo =========================================
echo.

:: Проверка прав администратора
net session >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Этот скрипт необходимо запустить от имени администратора!
    echo Кликните правой кнопкой мыши и выберите "Запуск от имени администратора".
    pause
    exit /b 1
)

:: Проверка наличия start.bat
if not exist "%START_SCRIPT%" (
    echo [ОШИБКА] Скрипт запуска не найден: %START_SCRIPT%
    pause
    exit /b 1
)

:: Удаление существующей задачи (если есть)
schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if not errorlevel 1 (
    echo Существующая задача "%TASK_NAME%" найдена. Обновление...
    schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
)

:: Создание задачи
echo Создание задачи в Task Scheduler...
echo   Имя:     %TASK_NAME%
echo   Триггер: При загрузке системы
echo   Задержка: 2 минуты
echo   Скрипт:  %START_SCRIPT%
echo.

schtasks /Create ^
    /TN "%TASK_NAME%" ^
    /TR "\"%START_SCRIPT%\"" ^
    /SC ONSTART ^
    /DELAY %DELAY% ^
    /RL HIGHEST ^
    /F

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось создать задачу.
    echo Попробуйте создать задачу вручную через Task Scheduler:
    echo   1. Откройте taskschd.msc
    echo   2. Создайте задачу "%TASK_NAME%"
    echo   3. Триггер: "При запуске компьютера" с задержкой 2 мин
    echo   4. Действие: Запуск "%START_SCRIPT%"
    echo   5. Установите "Выполнять с наивысшими правами"
    pause
    exit /b 1
)

echo.
echo =========================================
echo  Задача создана успешно!
echo =========================================
echo.
echo  Задача:   %TASK_NAME%
echo  Триггер:  При загрузке + 2 мин задержка
echo  Скрипт:   %START_SCRIPT%
echo.
echo  Проверить: schtasks /Query /TN "%TASK_NAME%" /V
echo  Удалить:   schtasks /Delete /TN "%TASK_NAME%" /F
echo  Запустить: schtasks /Run /TN "%TASK_NAME%"
echo.
pause
