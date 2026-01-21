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
import os

def run_bot():
    """Start both the telegram bot and image queue processor."""
    
    print("🚀 Starting SPRINT Fake Location Overlay Bot...\n")
    
    # Start telegram bot in a subprocess
    print("📱 Starting Telegram Bot...")
    telegram_process = subprocess.Popen(
        [sys.executable, "-m", "src.sbs_helper_telegram_bot.telegram_bot.telegram_bot"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Start image queue processor in a subprocess
    print("🖼️  Starting Image Queue Processor...")
    queue_process = subprocess.Popen(
        [sys.executable, "-m", "src.sbs_helper_telegram_bot.vyezd_byl.processimagequeue"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    print("✅ Both services started!\n")
    print("Press Ctrl+C to stop all services.\n")
    
    # Display output from both processes
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
            print("❌ All services have stopped.")
            sys.exit(1)
        elif telegram_poll is not None:
            print("❌ Telegram bot stopped unexpectedly.")
        elif queue_poll is not None:
            print("❌ Image queue processor stopped unexpectedly.")


if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user.")
        sys.exit(0)
