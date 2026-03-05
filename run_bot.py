#!/usr/bin/env python3
"""
run_bot.py

Простой скрипт для запуска Telegram-бота и фоновых воркеров.
Чтобы запустить всё приложение, выполните:

    python run_bot.py
"""

import subprocess
import sys
import signal
import threading
import time

# Настройки перезапуска
RESTART_DELAY_SECONDS = 5  # Ожидать N секунд перед перезапуском упавшего процесса
MAX_RESTART_ATTEMPTS = 3   # Максимальное число попыток перезапуска для процесса

def output_reader(process, prefix, stop_event):
    """Читать и печатать вывод подпроцесса с префиксом."""
    while not stop_event.is_set():
        line = process.stdout.readline()
        if line:
            print(f"[{prefix}] {line.rstrip()}")
        elif process.poll() is not None:
            break


def start_telegram_bot():
    """Запустить подпроцесс Telegram-бота."""
    return subprocess.Popen(
        [sys.executable, "-m", "src.sbs_helper_telegram_bot.telegram_bot.telegram_bot"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )


def start_queue_processor():
    """Запустить подпроцесс обработчика очереди изображений."""
    return subprocess.Popen(
        [sys.executable, "-m", "src.sbs_helper_telegram_bot.vyezd_byl.processimagequeue"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )


def start_soos_queue_processor():
    """Запустить подпроцесс обработчика очереди СООС."""
    return subprocess.Popen(
        [sys.executable, "-m", "src.sbs_helper_telegram_bot.soos.processimagequeue"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )


def start_health_check_daemon():
    """Запустить подпроцесс проверки доступности сервиса налоговой."""
    return subprocess.Popen(
        [sys.executable, "-m", "src.sbs_helper_telegram_bot.health_check.health_check_daemon"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )


def start_output_thread(process, prefix, stop_event):
    """Запустить поток для чтения вывода процесса."""
    thread = threading.Thread(target=output_reader, args=(process, prefix, stop_event), daemon=True)
    thread.start()
    return thread


def run_bot():
    """Запустить Telegram-бота и фоновые обработчики очередей."""
    
    print("🚀 Starting SBS Archie...\n")
    
    # Отслеживаем попытки перезапуска для каждого процесса
    telegram_restart_count = 0
    queue_restart_count = 0
    soos_restart_count = 0
    health_restart_count = 0
    
    # События остановки для потоков чтения вывода
    telegram_stop_event = threading.Event()
    queue_stop_event = threading.Event()
    soos_stop_event = threading.Event()
    health_stop_event = threading.Event()
    
    # Запускаем Telegram-бота в подпроцессе
    print("📱 Starting Telegram Bot...")
    telegram_process = start_telegram_bot()
    
    # Запускаем обработчик очереди изображений в подпроцессе
    print("🖼️  Starting Image Queue Processor...")
    queue_process = start_queue_processor()

    print("🧾 Starting SOOS Queue Processor...")
    soos_process = start_soos_queue_processor()

    # Запускаем проверку доступности сервиса налоговой
    print("🩺 Starting Tax Service Health Check...")
    health_process = start_health_check_daemon()
    
    # Запускаем потоки чтения вывода для обоих процессов
    telegram_thread = start_output_thread(telegram_process, "BOT", telegram_stop_event)
    queue_thread = start_output_thread(queue_process, "QUEUE", queue_stop_event)
    soos_thread = start_output_thread(soos_process, "SOOS", soos_stop_event)
    health_thread = start_output_thread(health_process, "HEALTH", health_stop_event)
    
    print("✅ All services started!\n")
    print("Press Ctrl+C to stop all services.\n")
    
    # Корректно обрабатываем Ctrl+C
    def signal_handler(sig, frame):
        print("\n\n🛑 Stopping services...")
        telegram_process.terminate()
        queue_process.terminate()
        soos_process.terminate()
        health_process.terminate()
        try:
            telegram_process.wait(timeout=5)
            queue_process.wait(timeout=5)
            soos_process.wait(timeout=5)
            health_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            telegram_process.kill()
            queue_process.kill()
            soos_process.kill()
            health_process.kill()
        print("✅ All services stopped.")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Ждём оба процесса
    while True:
        telegram_poll = telegram_process.poll()
        queue_poll = queue_process.poll()
        soos_poll = soos_process.poll()
        health_poll = health_process.poll()
        
        if telegram_poll is not None and queue_poll is not None and soos_poll is not None and health_poll is not None:
            # Все процессы остановились — пробуем перезапустить
            if (
                telegram_restart_count < MAX_RESTART_ATTEMPTS
                and queue_restart_count < MAX_RESTART_ATTEMPTS
                and soos_restart_count < MAX_RESTART_ATTEMPTS
                and health_restart_count < MAX_RESTART_ATTEMPTS
            ):
                print(f"⚠️  All services stopped. Restarting in {RESTART_DELAY_SECONDS} seconds...")
                time.sleep(RESTART_DELAY_SECONDS)
                
                telegram_stop_event.set()
                queue_stop_event.set()
                soos_stop_event.set()
                health_stop_event.set()
                telegram_stop_event = threading.Event()
                queue_stop_event = threading.Event()
                soos_stop_event = threading.Event()
                health_stop_event = threading.Event()
                
                print(f"🔄 Restarting Telegram Bot (attempt {telegram_restart_count + 1}/{MAX_RESTART_ATTEMPTS})...")
                telegram_process = start_telegram_bot()
                telegram_thread = start_output_thread(telegram_process, "BOT", telegram_stop_event)
                telegram_restart_count += 1
                
                print(f"🔄 Restarting Image Queue Processor (attempt {queue_restart_count + 1}/{MAX_RESTART_ATTEMPTS})...")
                queue_process = start_queue_processor()
                queue_thread = start_output_thread(queue_process, "QUEUE", queue_stop_event)
                queue_restart_count += 1

                print(f"🔄 Restarting SOOS Queue Processor (attempt {soos_restart_count + 1}/{MAX_RESTART_ATTEMPTS})...")
                soos_process = start_soos_queue_processor()
                soos_thread = start_output_thread(soos_process, "SOOS", soos_stop_event)
                soos_restart_count += 1

                print(f"🔄 Restarting Health Check (attempt {health_restart_count + 1}/{MAX_RESTART_ATTEMPTS})...")
                health_process = start_health_check_daemon()
                health_thread = start_output_thread(health_process, "HEALTH", health_stop_event)
                health_restart_count += 1
            else:
                print("❌ All services have stopped and max restart attempts reached.")
                sys.exit(1)
                
        elif telegram_poll is not None:
            if telegram_restart_count < MAX_RESTART_ATTEMPTS:
                telegram_restart_count += 1
                print(f"⚠️  Telegram bot stopped unexpectedly. Restarting in {RESTART_DELAY_SECONDS} seconds... (attempt {telegram_restart_count}/{MAX_RESTART_ATTEMPTS})")
                time.sleep(RESTART_DELAY_SECONDS)
                
                telegram_stop_event.set()
                telegram_stop_event = threading.Event()
                
                print(f"🔄 Restarting Telegram Bot...")
                telegram_process = start_telegram_bot()
                telegram_thread = start_output_thread(telegram_process, "BOT", telegram_stop_event)
            else:
                print(f"❌ Telegram bot stopped unexpectedly. Max restart attempts ({MAX_RESTART_ATTEMPTS}) reached.")
                queue_process.terminate()
                soos_process.terminate()
                health_process.terminate()
                sys.exit(1)
                
        elif queue_poll is not None:
            if queue_restart_count < MAX_RESTART_ATTEMPTS:
                queue_restart_count += 1
                print(f"⚠️  Image queue processor stopped unexpectedly. Restarting in {RESTART_DELAY_SECONDS} seconds... (attempt {queue_restart_count}/{MAX_RESTART_ATTEMPTS})")
                time.sleep(RESTART_DELAY_SECONDS)
                
                queue_stop_event.set()
                queue_stop_event = threading.Event()
                
                print(f"🔄 Restarting Image Queue Processor...")
                queue_process = start_queue_processor()
                queue_thread = start_output_thread(queue_process, "QUEUE", queue_stop_event)
            else:
                print(f"❌ Image queue processor stopped unexpectedly. Max restart attempts ({MAX_RESTART_ATTEMPTS}) reached.")
                telegram_process.terminate()
                soos_process.terminate()
                health_process.terminate()
                sys.exit(1)

        elif soos_poll is not None:
            if soos_restart_count < MAX_RESTART_ATTEMPTS:
                soos_restart_count += 1
                print(f"⚠️  SOOS queue processor stopped unexpectedly. Restarting in {RESTART_DELAY_SECONDS} seconds... (attempt {soos_restart_count}/{MAX_RESTART_ATTEMPTS})")
                time.sleep(RESTART_DELAY_SECONDS)

                soos_stop_event.set()
                soos_stop_event = threading.Event()

                print("🔄 Restarting SOOS Queue Processor...")
                soos_process = start_soos_queue_processor()
                soos_thread = start_output_thread(soos_process, "SOOS", soos_stop_event)
            else:
                print(f"❌ SOOS queue processor stopped unexpectedly. Max restart attempts ({MAX_RESTART_ATTEMPTS}) reached.")
                telegram_process.terminate()
                queue_process.terminate()
                health_process.terminate()
                sys.exit(1)

        elif health_poll is not None:
            if health_restart_count < MAX_RESTART_ATTEMPTS:
                health_restart_count += 1
                print(f"⚠️  Health check stopped unexpectedly. Restarting in {RESTART_DELAY_SECONDS} seconds... (attempt {health_restart_count}/{MAX_RESTART_ATTEMPTS})")
                time.sleep(RESTART_DELAY_SECONDS)

                health_stop_event.set()
                health_stop_event = threading.Event()

                print("🔄 Restarting Health Check...")
                health_process = start_health_check_daemon()
                health_thread = start_output_thread(health_process, "HEALTH", health_stop_event)
            else:
                print(f"❌ Health check stopped unexpectedly. Max restart attempts ({MAX_RESTART_ATTEMPTS}) reached.")
                telegram_process.terminate()
                queue_process.terminate()
                soos_process.terminate()
                sys.exit(1)
        
        time.sleep(0.5)  # Небольшая пауза, чтобы избежать активного ожидания


if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user.")
        sys.exit(0)
