#!/usr/bin/env python3
"""
run_bot.py

Simple script to start both the Telegram bot and the image processing queue worker.
Run this to start the entire application:

    python run_bot.py
"""

import subprocess
import sys
import signal
import threading
import time

# Restart settings
RESTART_DELAY_SECONDS = 5  # Wait N seconds before restarting a failed process
MAX_RESTART_ATTEMPTS = 3   # Maximum number of restart attempts per process

def output_reader(process, prefix, stop_event):
    """Read and print output from subprocess with a prefix."""
    while not stop_event.is_set():
        line = process.stdout.readline()
        if line:
            print(f"[{prefix}] {line.rstrip()}")
        elif process.poll() is not None:
            break


def start_telegram_bot():
    """Start the telegram bot subprocess."""
    return subprocess.Popen(
        [sys.executable, "-m", "src.sbs_helper_telegram_bot.telegram_bot.telegram_bot"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )


def start_queue_processor():
    """Start the image queue processor subprocess."""
    return subprocess.Popen(
        [sys.executable, "-m", "src.sbs_helper_telegram_bot.vyezd_byl.processimagequeue"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )


def start_output_thread(process, prefix, stop_event):
    """Start a thread to read output from a process."""
    thread = threading.Thread(target=output_reader, args=(process, prefix, stop_event), daemon=True)
    thread.start()
    return thread


def run_bot():
    """Start both the telegram bot and image queue processor."""
    
    print("🚀 Starting SPRINT Fake Location Overlay Bot...\n")
    
    # Track restart attempts for each process
    telegram_restart_count = 0
    queue_restart_count = 0
    
    # Stop events for output threads
    telegram_stop_event = threading.Event()
    queue_stop_event = threading.Event()
    
    # Start telegram bot in a subprocess
    print("📱 Starting Telegram Bot...")
    telegram_process = start_telegram_bot()
    
    # Start image queue processor in a subprocess
    print("🖼️  Starting Image Queue Processor...")
    queue_process = start_queue_processor()
    
    # Start threads to read output from both processes
    telegram_thread = start_output_thread(telegram_process, "BOT", telegram_stop_event)
    queue_thread = start_output_thread(queue_process, "QUEUE", queue_stop_event)
    
    print("✅ Both services started!\n")
    print("Press Ctrl+C to stop all services.\n")
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n\n🛑 Stopping services...")
        telegram_process.terminate()
        queue_process.terminate()
        try:
            telegram_process.wait(timeout=5)
            queue_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            telegram_process.kill()
            queue_process.kill()
        print("✅ All services stopped.")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Wait for both processes
    while True:
        telegram_poll = telegram_process.poll()
        queue_poll = queue_process.poll()
        
        if telegram_poll is not None and queue_poll is not None:
            # Both processes stopped - try to restart both
            if telegram_restart_count < MAX_RESTART_ATTEMPTS and queue_restart_count < MAX_RESTART_ATTEMPTS:
                print(f"⚠️  Both services stopped. Restarting in {RESTART_DELAY_SECONDS} seconds...")
                time.sleep(RESTART_DELAY_SECONDS)
                
                telegram_stop_event.set()
                queue_stop_event.set()
                telegram_stop_event = threading.Event()
                queue_stop_event = threading.Event()
                
                print(f"🔄 Restarting Telegram Bot (attempt {telegram_restart_count + 1}/{MAX_RESTART_ATTEMPTS})...")
                telegram_process = start_telegram_bot()
                telegram_thread = start_output_thread(telegram_process, "BOT", telegram_stop_event)
                telegram_restart_count += 1
                
                print(f"🔄 Restarting Image Queue Processor (attempt {queue_restart_count + 1}/{MAX_RESTART_ATTEMPTS})...")
                queue_process = start_queue_processor()
                queue_thread = start_output_thread(queue_process, "QUEUE", queue_stop_event)
                queue_restart_count += 1
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
                sys.exit(1)
        
        time.sleep(0.5)  # Small delay to prevent busy-waiting


if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user.")
        sys.exit(0)
