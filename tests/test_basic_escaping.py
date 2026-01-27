#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple test to validate the specific messages we fixed.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.messages import MESSAGE_WELCOME, MESSAGE_MAIN_HELP, MESSAGE_PLEASE_ENTER_INVITE


def test_basic_escaping():
    """Test the basic escaping issues we should have fixed."""
    
    print("Testing MESSAGE_WELCOME...")
    print(f"Content: {MESSAGE_WELCOME[:100]}...")
    
    # Test for properly escaped GitHub URL
    if "github\\.com" in MESSAGE_WELCOME and "sbs\\_helper\\_telegram\\_bot" in MESSAGE_WELCOME:
        print("✅ GitHub URL is properly escaped")
    else:
        print("❌ GitHub URL is NOT properly escaped")
        return False
    
    print("\nTesting MESSAGE_MAIN_HELP...")
    print(f"Content: {MESSAGE_MAIN_HELP[:100]}...")
    
    # Test for properly escaped GitHub URL
    if "github\\.com" in MESSAGE_MAIN_HELP and "sbs\\_helper\\_telegram\\_bot" in MESSAGE_MAIN_HELP:
        print("✅ GitHub URL is properly escaped")
    else:
        print("❌ GitHub URL is NOT properly escaped")
        return False
        
    print("\nTesting MESSAGE_PLEASE_ENTER_INVITE...")
    print(f"Content: {MESSAGE_PLEASE_ENTER_INVITE}")
    
    # Test for properly escaped periods
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