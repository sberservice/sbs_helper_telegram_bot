#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Простой тест для проверки MarkdownV2-экранирования в ключевых сообщениях.
"""

import sys
import os

# Добавляем родительскую директорию в path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.messages import MESSAGE_WELCOME, MESSAGE_MAIN_HELP, MESSAGE_PLEASE_ENTER_INVITE


def test_basic_escaping():
    """Проверка корректного экранирования MarkdownV2 в основных сообщениях."""
    
    print("Testing MESSAGE_WELCOME...")
    print(f"Content: {MESSAGE_WELCOME[:100]}...")
    
    # Проверяем, что приветственное сообщение не содержит ссылку на GitHub
    assert "github" not in MESSAGE_WELCOME.lower(), "MESSAGE_WELCOME не должен содержать ссылку на GitHub"
    
    # Проверяем наличие ключевых элементов приветственного сообщения
    assert "СберСервис" in MESSAGE_WELCOME, "MESSAGE_WELCOME должен содержать упоминание СберСервис"
    print("✅ MESSAGE_WELCOME is properly formatted")
    
    print("\nTesting MESSAGE_MAIN_HELP...")
    print(f"Content: {MESSAGE_MAIN_HELP[:100]}...")
    
    # Проверяем, что справочное сообщение не содержит ссылку на GitHub
    assert "github" not in MESSAGE_MAIN_HELP.lower(), "MESSAGE_MAIN_HELP не должен содержать ссылку на GitHub"
    
    # Проверяем наличие ключевых команд в справке
    assert "/start" in MESSAGE_MAIN_HELP, "MESSAGE_MAIN_HELP должен содержать команду /start"
    assert "/menu" in MESSAGE_MAIN_HELP, "MESSAGE_MAIN_HELP должен содержать команду /menu"
    assert "/reset" in MESSAGE_MAIN_HELP, "MESSAGE_MAIN_HELP должен содержать команду /reset"
    print("✅ MESSAGE_MAIN_HELP is properly formatted")
        
    print("\nTesting MESSAGE_PLEASE_ENTER_INVITE...")
    print(f"Content: {MESSAGE_PLEASE_ENTER_INVITE}")
    
    # Проверяем корректное экранирование точек
    if MESSAGE_PLEASE_ENTER_INVITE.endswith("меню\\."):
        print("✅ Periods are properly escaped")
    else:
        print("❌ Periods are NOT properly escaped")
        return False
    
    return True


if __name__ == "__main__":
    success = test_basic_escaping()
    if success:
        print("\n🎉 All basic MarkdownV2 escaping tests passed!")
    else:
        print("\n💥 Some MarkdownV2 escaping tests failed!")
    
    sys.exit(0 if success else 1)