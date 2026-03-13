@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

REM ============================================================
REM SBS Archie — CUDA окружение (setup_cuda.bat)
REM Создаёт/обновляет venv для GPU-окружения и устанавливает
REM PyTorch CUDA-сборку (вместо CPU).
REM ============================================================

set "PROJECT_DIR=C:\SBS_Archie"
set "VENV_DIR=%PROJECT_DIR%\venv_name"
set "REQ_FILE=%PROJECT_DIR%\requirements.txt"
set "REQ_NO_TORCH=%TEMP%\requirements_sbs_no_torch_%RANDOM%.txt"
set "TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124"

echo =========================================
echo  SBS Archie — Настройка CUDA окружения
echo =========================================
echo.

cd /d "%PROJECT_DIR%" || (
    echo [ОШИБКА] Директория проекта не найдена: %PROJECT_DIR%
    pause
    exit /b 1
)

if not exist "%REQ_FILE%" (
    echo [ОШИБКА] Файл requirements.txt не найден: %REQ_FILE%
    pause
    exit /b 1
)

echo [1/7] Проверка NVIDIA GPU...
where nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] nvidia-smi не найден. Установите драйвер NVIDIA и CUDA runtime на сервер.
    pause
    exit /b 1
)
nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] NVIDIA GPU недоступен ^(nvidia-smi завершился с ошибкой^).
    pause
    exit /b 1
)
echo   NVIDIA GPU обнаружен.
echo.

echo [2/7] Подготовка Python 3.11/3.12...
set "PYTHON_EXE="
where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=py -3.12"
    )
)
if not defined PYTHON_EXE (
    where python >nul 2>&1 || (
        echo [ОШИБКА] Python не найден. Установите Python 3.11 или 3.12.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=python"
)
echo   Используется: %PYTHON_EXE%
echo.

echo [3/7] Создание/проверка venv...
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    %PYTHON_EXE% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать venv: %VENV_DIR%
        pause
        exit /b 1
    )
    echo   venv создан: %VENV_DIR%
) else (
    echo   venv уже существует: %VENV_DIR%
)
call "%VENV_DIR%\Scripts\activate.bat"

for /f "tokens=1,2 delims=." %%a in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do (
    set "PY_MAJ=%%a"
    set "PY_MIN=%%b"
)
if %PY_MAJ% EQU 3 if %PY_MIN% GEQ 13 (
    echo [ОШИБКА] Для CUDA PyTorch рекомендуется Python 3.11/3.12. Текущая версия: %PY_MAJ%.%PY_MIN%
    echo Переустановите venv через Python 3.11/3.12 и повторите запуск setup_cuda.bat.
    pause
    exit /b 1
)
echo   Версия Python в venv: %PY_MAJ%.%PY_MIN%
echo.

echo [4/7] Установка зависимостей без torch...
findstr /V /I "torch== torchvision== torchaudio==" "%REQ_FILE%" > "%REQ_NO_TORCH%"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось сформировать requirements без torch.
    pause
    exit /b 1
)
python -m pip install --upgrade pip
if errorlevel 1 (
    echo [ОШИБКА] Не удалось обновить pip.
    del "%REQ_NO_TORCH%" >nul 2>&1
    pause
    exit /b 1
)
python -m pip install -r "%REQ_NO_TORCH%"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить зависимости без torch.
    del "%REQ_NO_TORCH%" >nul 2>&1
    pause
    exit /b 1
)
del "%REQ_NO_TORCH%" >nul 2>&1
echo   Базовые зависимости установлены.
echo.

echo [5/7] Установка PyTorch CUDA из %TORCH_INDEX_URL% ...
python -m pip uninstall -y torch torchvision torchaudio >nul 2>&1
python -m pip install torch torchvision torchaudio --index-url %TORCH_INDEX_URL%
if errorlevel 1 (
    echo [ОШИБКА] Установка CUDA-сборки PyTorch не удалась.
    pause
    exit /b 1
)
echo   CUDA-сборка PyTorch установлена.
echo.

echo [6/7] Проверка CUDA в Python...
python -c "import torch,sys; print('python=', sys.executable); print('torch=', torch.__version__); print('cuda_available=', torch.cuda.is_available()); print('cuda_version=', torch.version.cuda); print('device_count=', torch.cuda.device_count()); print('device_name=', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
if errorlevel 1 (
    echo [ОШИБКА] Проверка CUDA завершилась с ошибкой.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python -c "import torch; print(int(torch.cuda.is_available()))"') do set "CUDA_READY=%%v"
if not "%CUDA_READY%"=="1" (
    echo [ОШИБКА] torch.cuda.is_available^(^) == False.
    echo Проверьте совместимость драйвера NVIDIA, CUDA runtime и версию Python.
    pause
    exit /b 1
)
echo   CUDA доступна для PyTorch.
echo.

echo [7/7] Готово.
echo.
echo =========================================
echo  CUDA окружение готово
echo =========================================
echo После этого можно запускать deploy\start.bat.
echo При каждом deploy\update.bat повторно запускайте deploy\setup_cuda.bat,
echo чтобы не вернуться на CPU-сборку torch.
echo =========================================
pause
