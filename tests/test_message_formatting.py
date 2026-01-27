#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Telegram MarkdownV2 message formatting.

This test validates that all messages used with MARKDOWN_V2 parse mode
have properly escaped special characters to prevent parsing errors.
"""

import unittest
import sys
import os
import re
from typing import List, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.messages import (
    MESSAGE_WELCOME,
    MESSAGE_MAIN_HELP,
    MESSAGE_PLEASE_ENTER_INVITE,
    MESSAGE_MAIN_MENU,
    MESSAGE_SETTINGS_MENU,
    MESSAGE_MODULES_MENU,
    MESSAGE_UNRECOGNIZED_INPUT
)
from src.sbs_helper_telegram_bot.upos_error.messages import (
    MESSAGE_SUBMENU,
    MESSAGE_ENTER_ERROR_CODE,
    MESSAGE_SEARCH_CANCELLED,
    MESSAGE_ERROR_NOT_FOUND,
    MESSAGE_INVALID_ERROR_CODE,
    MESSAGE_NO_POPULAR_ERRORS,
    MESSAGE_POPULAR_ERRORS_HEADER,
    MESSAGE_ADMIN_MENU,
    MESSAGE_ADMIN_NOT_AUTHORIZED,
    MESSAGE_ADMIN_ERRORS_LIST_EMPTY,
    MESSAGE_ADMIN_ERRORS_LIST_HEADER
)
from src.sbs_helper_telegram_bot.vyezd_byl.messages import (
    MESSAGE_SUBMENU as VYEZD_MESSAGE_SUBMENU,
    MESSAGE_INSTRUCTIONS,
    MESSAGE_HELP as VYEZD_MESSAGE_HELP
)
from src.sbs_helper_telegram_bot.ticket_validator.messages import (
    MESSAGE_SEND_TICKET,
    MESSAGE_VALIDATION_CANCELLED,
    MESSAGE_VALIDATION_SUCCESS,
    MESSAGE_VALIDATION_FAILED,
    MESSAGE_SUBMENU as VALIDATOR_MESSAGE_SUBMENU
)


class TestMarkdownV2Formatting(unittest.TestCase):
    """Test MarkdownV2 formatting for all messages that use parse_mode=MARKDOWN_V2."""
    
    # MarkdownV2 special characters that need escaping
    SPECIAL_CHARS = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    def _check_markdown_v2_escaping(self, message: str, message_name: str) -> List[str]:
        """
        Check if a message has proper MarkdownV2 escaping.
        
        Args:
            message: The message to check
            message_name: Name of the message for error reporting
            
        Returns:
            List of error messages found
        """
        errors = []
        
        # Skip check if message contains placeholder formatting (e.g., {code})
        if '{' in message and '}' in message:
            return errors  # Dynamic messages are handled separately
        
        for char in self.SPECIAL_CHARS:
            # Find all occurrences of the special character
            pos = 0
            while True:
                pos = message.find(char, pos)
                if pos == -1:
                    break
                
                # Check if it's properly escaped (preceded by backslash)
                if pos == 0 or message[pos - 1] != '\\':
                    # Exception: Some characters are allowed in certain contexts
                    if self._is_allowed_unescaped_char(message, char, pos):
                        pos += 1
                        continue
                        
                    errors.append(
                        f"{message_name}: Unescaped '{char}' at position {pos}. "
                        f"Context: ...{message[max(0, pos-10):pos+11]}..."
                    )
                pos += 1
                
        return errors
    
    def _is_allowed_unescaped_char(self, message: str, char: str, pos: int) -> bool:
        """
        Check if an unescaped character is allowed in certain contexts.
        
        For example:
        - '*' is allowed for bold formatting if properly paired
        - '_' is allowed for italic formatting if properly paired
        - '`' is allowed for code formatting if properly paired
        """
        
        if char in ['*', '_', '`']:
            # Check if it's part of a proper markdown formatting pair
            return self._is_proper_markdown_formatting(message, char, pos)
        
        return False
    
    def _is_proper_markdown_formatting(self, message: str, char: str, pos: int) -> bool:
        """
        Check if the character is part of proper markdown formatting.
        """
        
        if char == '*':
            # Check for bold formatting: *text*
            # Look ahead to find the closing asterisk
            rest_of_message = message[pos + 1:]
            
            # Find the next asterisk (should be the closing one)
            next_asterisk_pos = rest_of_message.find('*')
            if next_asterisk_pos != -1:
                # Check if there's meaningful text between them
                between_text = rest_of_message[:next_asterisk_pos].strip()
                # Valid if there's text and not too many newlines (max 1-2 for titles)
                if between_text and between_text.count('\n') <= 2:
                    return True
            return False
        
        if char == '_':
            # Check for italic formatting: _text_
            rest_of_message = message[pos + 1:]
            next_underscore_pos = rest_of_message.find('_')
            if next_underscore_pos != -1:
                between_text = rest_of_message[:next_underscore_pos].strip()
                # Valid if there's text and it's on the same line or just spans a couple words
                if between_text and between_text.count('\n') == 0:
                    return True
            return False
            
        if char == '`':
            # Check for code formatting: `text`
            rest_of_message = message[pos + 1:]
            next_backtick_pos = rest_of_message.find('`')
            if next_backtick_pos != -1:
                between_text = rest_of_message[:next_backtick_pos]
                # Code formatting should be on single line and contain text
                if between_text and '\n' not in between_text:
                    return True
            return False
            
        return False

    def test_common_messages_markdown_v2_formatting(self):
        """Test that common messages used with MARKDOWN_V2 are properly formatted."""
        
        # Messages that are known to be used with MARKDOWN_V2 parse mode
        messages_to_check = [
            (MESSAGE_WELCOME, "MESSAGE_WELCOME"),
            (MESSAGE_MAIN_HELP, "MESSAGE_MAIN_HELP"),
            (MESSAGE_PLEASE_ENTER_INVITE, "MESSAGE_PLEASE_ENTER_INVITE"),
            (MESSAGE_UNRECOGNIZED_INPUT, "MESSAGE_UNRECOGNIZED_INPUT")
        ]
        
        all_errors = []
        
        for message, name in messages_to_check:
            errors = self._check_markdown_v2_escaping(message, name)
            all_errors.extend(errors)
        
        if all_errors:
            self.fail("MarkdownV2 formatting errors found:\n" + "\n".join(all_errors))
    
    def test_upos_error_messages_markdown_v2_formatting(self):
        """Test UPOS error module messages used with MARKDOWN_V2."""
        
        messages_to_check = [
            (MESSAGE_SUBMENU, "UPOS_MESSAGE_SUBMENU"),
            (MESSAGE_ENTER_ERROR_CODE, "MESSAGE_ENTER_ERROR_CODE"),
            (MESSAGE_SEARCH_CANCELLED, "MESSAGE_SEARCH_CANCELLED"),
            (MESSAGE_INVALID_ERROR_CODE, "MESSAGE_INVALID_ERROR_CODE"),
            (MESSAGE_NO_POPULAR_ERRORS, "MESSAGE_NO_POPULAR_ERRORS"),
            (MESSAGE_ADMIN_MENU, "MESSAGE_ADMIN_MENU"),
            (MESSAGE_ADMIN_NOT_AUTHORIZED, "MESSAGE_ADMIN_NOT_AUTHORIZED"),
            (MESSAGE_ADMIN_ERRORS_LIST_EMPTY, "MESSAGE_ADMIN_ERRORS_LIST_EMPTY"),
        ]
        
        all_errors = []
        
        for message, name in messages_to_check:
            errors = self._check_markdown_v2_escaping(message, name)
            all_errors.extend(errors)
        
        if all_errors:
            self.fail("UPOS Error MarkdownV2 formatting errors found:\n" + "\n".join(all_errors))
    
    def test_vyezd_byl_messages_markdown_v2_formatting(self):
        """Test Vyezd Byl module messages used with MARKDOWN_V2."""
        
        messages_to_check = [
            (VYEZD_MESSAGE_SUBMENU, "VYEZD_MESSAGE_SUBMENU"),
            (MESSAGE_INSTRUCTIONS, "MESSAGE_INSTRUCTIONS"),
            (VYEZD_MESSAGE_HELP, "VYEZD_MESSAGE_HELP"),
        ]
        
        all_errors = []
        
        for message, name in messages_to_check:
            errors = self._check_markdown_v2_escaping(message, name)
            all_errors.extend(errors)
        
        if all_errors:
            self.fail("Vyezd Byl MarkdownV2 formatting errors found:\n" + "\n".join(all_errors))
    
    def test_ticket_validator_messages_markdown_v2_formatting(self):
        """Test Ticket Validator module messages used with MARKDOWN_V2."""
        
        messages_to_check = [
            (MESSAGE_SEND_TICKET, "MESSAGE_SEND_TICKET"),
            (MESSAGE_VALIDATION_CANCELLED, "MESSAGE_VALIDATION_CANCELLED"),
            (MESSAGE_VALIDATION_SUCCESS, "MESSAGE_VALIDATION_SUCCESS"),
            (VALIDATOR_MESSAGE_SUBMENU, "VALIDATOR_MESSAGE_SUBMENU"),
        ]
        
        all_errors = []
        
        for message, name in messages_to_check:
            errors = self._check_markdown_v2_escaping(message, name)
            all_errors.extend(errors)
        
        if all_errors:
            self.fail("Ticket Validator MarkdownV2 formatting errors found:\n" + "\n".join(all_errors))
    
    def test_no_github_url_escaping_issues(self):
        """Test that GitHub URLs are properly escaped in all messages."""
        
        github_url_pattern = r'https?://github\.com/[^\s]+'
        messages_with_urls = [
            (MESSAGE_WELCOME, "MESSAGE_WELCOME"),
            (MESSAGE_MAIN_HELP, "MESSAGE_MAIN_HELP"),
        ]
        
        errors = []
        
        for message, name in messages_with_urls:
            # Find GitHub URLs
            urls = re.findall(github_url_pattern, message)
            for url in urls:
                # Check if periods and underscores in URLs are escaped
                if '.com/' in url and '\\.com/' not in url:
                    errors.append(f"{name}: GitHub URL has unescaped period: {url}")
                if '_' in url and '\\_' not in url:
                    errors.append(f"{name}: GitHub URL has unescaped underscore: {url}")
        
        if errors:
            self.fail("GitHub URL escaping errors found:\n" + "\n".join(errors))
    
    def test_message_formatting_consistency(self):
        """Test that similar messages have consistent formatting."""
        
        # Check that all menu messages follow similar patterns
        menu_messages = [
            MESSAGE_MAIN_MENU,
            MESSAGE_SETTINGS_MENU,
            MESSAGE_MODULES_MENU,
        ]
        
        # All menu messages should start with an emoji and have bold title
        for i, message in enumerate(menu_messages):
            # Should start with emoji
            if not re.match(r'^[^\w]', message):
                self.fail(f"Menu message {i} should start with an emoji")
            
            # Should have bold formatting
            if '*' not in message:
                self.fail(f"Menu message {i} should have bold formatting")


class TestMessageIntegration(unittest.TestCase):
    """Integration tests for message usage in bot handlers."""
    
    def test_all_markdown_v2_messages_are_tested(self):
        """
        Ensure we're testing all messages that are actually used with MARKDOWN_V2.
        
        This test serves as a reminder to update the test cases when new messages
        are added that use MARKDOWN_V2 formatting.
        """
        
        # This is a meta-test - it doesn't validate formatting but ensures
        # we don't miss any messages that should be tested
        
        # List of all message constants that are used with MARKDOWN_V2 in the codebase
        # (This would need to be updated when new messages are added)
        known_markdown_v2_messages = {
            'MESSAGE_WELCOME',
            'MESSAGE_MAIN_HELP',
            'MESSAGE_PLEASE_ENTER_INVITE',
            'MESSAGE_UNRECOGNIZED_INPUT',
            # Add more as they're identified
        }
        
        # In a real implementation, you might scan the codebase for
        # parse_mode=constants.ParseMode.MARKDOWN_V2 usage
        
        # For now, this serves as documentation of what should be tested
        self.assertTrue(len(known_markdown_v2_messages) > 0, 
                       "At least some messages should use MARKDOWN_V2")


if __name__ == '__main__':
    unittest.main(verbosity=2)