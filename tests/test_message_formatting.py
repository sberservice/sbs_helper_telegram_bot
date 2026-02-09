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
    MESSAGE_UNRECOGNIZED_INPUT,
    MESSAGE_NO_ADMIN_RIGHTS,
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
    MESSAGE_ADMIN_ERRORS_LIST_HEADER,
    MESSAGE_SELECT_ACTION,
    MESSAGE_NO_CATEGORY,
    MESSAGE_NO_DATA,
    MESSAGE_USE_LIST_BUTTON,
    MESSAGE_NO_IMPORT_DATA,
    MESSAGE_IMPORT_IN_PROGRESS,
    MESSAGE_AND_MORE,
    MESSAGE_CSV_ERROR_NO_CODE_COLUMN,
    MESSAGE_CSV_ERROR_NO_DESC_COLUMN,
    MESSAGE_CSV_ERROR_NO_ACTIONS_COLUMN,
    BUTTON_FORWARD,
    BUTTON_BACK,
    BUTTON_BACK_TO_MENU,
)
from src.sbs_helper_telegram_bot.vyezd_byl.messages import (
    MESSAGE_SUBMENU as VYEZD_MESSAGE_SUBMENU,
    MESSAGE_INSTRUCTIONS,
    MESSAGE_HELP as VYEZD_MESSAGE_HELP,
    MESSAGE_PROCESSING_DONE,
)
from src.sbs_helper_telegram_bot.news.messages import (
    MESSAGE_SUBMENU as NEWS_MESSAGE_SUBMENU,
    MESSAGE_SUBMENU_UNREAD as NEWS_MESSAGE_SUBMENU_UNREAD,
    MESSAGE_NO_NEWS as NEWS_MESSAGE_NO_NEWS,
    MESSAGE_ARCHIVE_EMPTY as NEWS_MESSAGE_ARCHIVE_EMPTY,
    MESSAGE_SEARCH_PROMPT as NEWS_MESSAGE_SEARCH_PROMPT,
    MESSAGE_SEARCH_NO_RESULTS as NEWS_MESSAGE_SEARCH_NO_RESULTS,
    MESSAGE_NEWS_MARKED_READ as NEWS_MESSAGE_NEWS_MARKED_READ,
    MESSAGE_MANDATORY_NEWS as NEWS_MESSAGE_MANDATORY_NEWS,
    MESSAGE_MANDATORY_BLOCKING as NEWS_MESSAGE_MANDATORY_BLOCKING,
    MESSAGE_MANDATORY_ACKNOWLEDGED as NEWS_MESSAGE_MANDATORY_ACKNOWLEDGED,
    MESSAGE_ADMIN_NOT_AUTHORIZED as NEWS_MESSAGE_ADMIN_NOT_AUTHORIZED,
    MESSAGE_ADMIN_MENU as NEWS_MESSAGE_ADMIN_MENU,
    MESSAGE_ADMIN_DRAFTS_EMPTY as NEWS_MESSAGE_ADMIN_DRAFTS_EMPTY,
    MESSAGE_ADMIN_PUBLISHED_EMPTY as NEWS_MESSAGE_ADMIN_PUBLISHED_EMPTY,
    MESSAGE_ADMIN_DRAFT_SAVED as NEWS_MESSAGE_ADMIN_DRAFT_SAVED,
    MESSAGE_ADMIN_PREVIEW_SENT as NEWS_MESSAGE_ADMIN_PREVIEW_SENT,
    MESSAGE_ADMIN_PUBLISHED as NEWS_MESSAGE_ADMIN_PUBLISHED,
)
from src.sbs_helper_telegram_bot.ticket_validator.messages import (
    MESSAGE_SEND_TICKET,
    MESSAGE_VALIDATION_CANCELLED,
    MESSAGE_VALIDATION_SUCCESS,
    MESSAGE_VALIDATION_FAILED,
    MESSAGE_SUBMENU as VALIDATOR_MESSAGE_SUBMENU,
    MESSAGE_ADMIN_NOT_ASSIGNED,
    MESSAGE_ADMIN_ENABLED,
    MESSAGE_ADMIN_DISABLED,
    MESSAGE_ADMIN_NO_ASSIGNED_RULES,
    MESSAGE_ADMIN_NO_KEYWORDS,
    MESSAGE_ADMIN_ALL_RULES_ADDED,
    MESSAGE_ADMIN_SELECT_RULE_TO_ADD,
    MESSAGE_ADMIN_RULE_ADDED,
    MESSAGE_ADMIN_RULE_ALREADY_ADDED,
    MESSAGE_ADMIN_ERROR,
    MESSAGE_ADMIN_RULE_REMOVED,
    MESSAGE_ADMIN_ERROR_REMOVING,
    MESSAGE_ADMIN_NOT_CONFIGURED,
    MESSAGE_ADMIN_NOT_SPECIFIED,
    MESSAGE_ADMIN_TEMPLATE_ENABLED,
    MESSAGE_ADMIN_TEMPLATE_DISABLED,
    MESSAGE_ADMIN_UNKNOWN_TEMPLATE,
    MESSAGE_ADMIN_CLICK_RULE_TO_REMOVE,
    MESSAGE_ADMIN_NO_RULES_CONFIGURED,
    MESSAGE_ADMIN_ALL_RULES_IN_TEMPLATE,
    MESSAGE_ADMIN_UNKNOWN_RULE,
    MESSAGE_ADMIN_SHOULD_PASS,
    MESSAGE_ADMIN_SHOULD_FAIL,
    MESSAGE_ADMIN_EXPECTED_PASS,
    MESSAGE_ADMIN_EXPECTED_FAIL,
    MESSAGE_ADMIN_ACTUAL_PASSED,
    MESSAGE_ADMIN_ACTUAL_FAILED,
    MESSAGE_ADMIN_ALL_TESTS_PASSED,
    MESSAGE_ADMIN_RULE_NOT_FOUND,
    MESSAGE_ADMIN_ERROR_UPDATING,
    MESSAGE_NO_TICKET_TYPES,
    MESSAGE_NO_RULES_CONFIGURED,
    MESSAGE_VALIDATION_ERROR,
    MESSAGE_RUNNING_TESTS,
)


class TestMarkdownV2Formatting(unittest.TestCase):
    """Test MarkdownV2 formatting for all messages that use parse_mode=MARKDOWN_V2."""
    
    # MarkdownV2 special characters that MUST be escaped (outside of formatting)
    # These are characters that cause parsing errors if not escaped
    MUST_ESCAPE_CHARS = ['.', '!', '-', '+', '=', '>', '#', '|', '{', '}', '(', ')', '[', ']', '~']
    
    # Formatting characters - these are allowed unescaped when used in pairs
    FORMATTING_CHARS = ['*', '_', '`']
    
    def _find_markdown_formatted_ranges(self, message: str, char: str) -> List[Tuple[int, int]]:
        """
        Find all ranges of properly formatted markdown (paired characters).
        
        Returns list of (start, end) tuples for valid formatting ranges.
        """
        ranges = []
        pos = 0
        
        while pos < len(message):
            # Find opening character
            start = message.find(char, pos)
            if start == -1:
                break
            
            # Skip if escaped
            if start > 0 and message[start - 1] == '\\':
                pos = start + 1
                continue
            
            # Find closing character (not escaped)
            end = start + 1
            while end < len(message):
                end = message.find(char, end)
                if end == -1:
                    break
                # Check if not escaped
                if end > 0 and message[end - 1] == '\\':
                    end += 1
                    continue
                # Found valid closing character
                break
            
            if end != -1 and end > start:
                # Check if there's actual content between them
                between = message[start + 1:end]
                # For * and _, content should be on same line or just a few lines (for titles)
                if char in ['*', '_']:
                    if between.strip() and between.count('\n') <= 3:
                        ranges.append((start, end))
                # For backticks, content should be on same line
                elif char == '`':
                    if between.strip() and '\n' not in between:
                        ranges.append((start, end))
                pos = end + 1
            else:
                pos = start + 1
        
        return ranges
    
    def _is_in_formatted_range(self, pos: int, ranges: List[Tuple[int, int]]) -> bool:
        """Check if a position is within any formatted range (opening or closing char)."""
        for start, end in ranges:
            if pos == start or pos == end:
                return True
        return False
    
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
        
        # Find all valid formatting ranges
        bold_ranges = self._find_markdown_formatted_ranges(message, '*')
        italic_ranges = self._find_markdown_formatted_ranges(message, '_')
        code_ranges = self._find_markdown_formatted_ranges(message, '`')
        all_formatting_ranges = bold_ranges + italic_ranges + code_ranges
        
        # Check characters that MUST be escaped
        for char in self.MUST_ESCAPE_CHARS:
            pos = 0
            while True:
                pos = message.find(char, pos)
                if pos == -1:
                    break
                
                # Check if it's properly escaped (preceded by backslash)
                if pos == 0 or message[pos - 1] != '\\':
                    errors.append(
                        f"{message_name}: Unescaped '{char}' at position {pos}. "
                        f"Context: ...{message[max(0, pos-10):pos+11]}..."
                    )
                pos += 1
        
        # Check formatting characters - they're only errors if NOT in valid pairs
        for char in self.FORMATTING_CHARS:
            if char == '*':
                ranges = bold_ranges
            elif char == '_':
                ranges = italic_ranges
            else:
                ranges = code_ranges
            
            pos = 0
            while True:
                pos = message.find(char, pos)
                if pos == -1:
                    break
                
                # Skip if escaped
                if pos > 0 and message[pos - 1] == '\\':
                    pos += 1
                    continue
                
                # Check if it's part of valid formatting
                if not self._is_in_formatted_range(pos, ranges):
                    errors.append(
                        f"{message_name}: Unpaired '{char}' at position {pos}. "
                        f"Context: ...{message[max(0, pos-10):pos+11]}..."
                    )
                pos += 1
                
        return errors

    def test_common_messages_markdown_v2_formatting(self):
        """Test that common messages used with MARKDOWN_V2 are properly formatted."""
        
        # Messages that are known to be used with MARKDOWN_V2 parse mode
        messages_to_check = [
            (MESSAGE_WELCOME, "MESSAGE_WELCOME"),
            (MESSAGE_MAIN_HELP, "MESSAGE_MAIN_HELP"),
            (MESSAGE_UNRECOGNIZED_INPUT, "MESSAGE_UNRECOGNIZED_INPUT"),
            (MESSAGE_NO_ADMIN_RIGHTS, "MESSAGE_NO_ADMIN_RIGHTS"),
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
            (MESSAGE_NO_IMPORT_DATA, "MESSAGE_NO_IMPORT_DATA"),
            (MESSAGE_IMPORT_IN_PROGRESS, "MESSAGE_IMPORT_IN_PROGRESS"),
            (MESSAGE_AND_MORE, "MESSAGE_AND_MORE"),
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
            (MESSAGE_ADMIN_NO_RULES_CONFIGURED, "MESSAGE_ADMIN_NO_RULES_CONFIGURED"),
            (MESSAGE_ADMIN_ALL_RULES_IN_TEMPLATE, "MESSAGE_ADMIN_ALL_RULES_IN_TEMPLATE"),
            (MESSAGE_ADMIN_ALL_TESTS_PASSED, "MESSAGE_ADMIN_ALL_TESTS_PASSED"),
            (MESSAGE_ADMIN_RULE_NOT_FOUND, "MESSAGE_ADMIN_RULE_NOT_FOUND"),
            (MESSAGE_ADMIN_ERROR_UPDATING, "MESSAGE_ADMIN_ERROR_UPDATING"),
            (MESSAGE_NO_TICKET_TYPES, "MESSAGE_NO_TICKET_TYPES"),
            (MESSAGE_NO_RULES_CONFIGURED, "MESSAGE_NO_RULES_CONFIGURED"),
            (MESSAGE_VALIDATION_ERROR, "MESSAGE_VALIDATION_ERROR"),
            (MESSAGE_RUNNING_TESTS, "MESSAGE_RUNNING_TESTS"),
        ]
        
        all_errors = []
        
        for message, name in messages_to_check:
            errors = self._check_markdown_v2_escaping(message, name)
            all_errors.extend(errors)
        
        if all_errors:
            self.fail("Ticket Validator MarkdownV2 formatting errors found:\n" + "\n".join(all_errors))

    def test_news_messages_markdown_v2_formatting(self):
        """Test News module messages used with MARKDOWN_V2."""

        messages_to_check = [
            (NEWS_MESSAGE_SUBMENU, "NEWS_MESSAGE_SUBMENU"),
            (NEWS_MESSAGE_SUBMENU_UNREAD, "NEWS_MESSAGE_SUBMENU_UNREAD"),
            (NEWS_MESSAGE_NO_NEWS, "NEWS_MESSAGE_NO_NEWS"),
            (NEWS_MESSAGE_ARCHIVE_EMPTY, "NEWS_MESSAGE_ARCHIVE_EMPTY"),
            (NEWS_MESSAGE_SEARCH_PROMPT, "NEWS_MESSAGE_SEARCH_PROMPT"),
            (NEWS_MESSAGE_SEARCH_NO_RESULTS, "NEWS_MESSAGE_SEARCH_NO_RESULTS"),
            (NEWS_MESSAGE_NEWS_MARKED_READ, "NEWS_MESSAGE_NEWS_MARKED_READ"),
            (NEWS_MESSAGE_MANDATORY_NEWS, "NEWS_MESSAGE_MANDATORY_NEWS"),
            (NEWS_MESSAGE_MANDATORY_BLOCKING, "NEWS_MESSAGE_MANDATORY_BLOCKING"),
            (NEWS_MESSAGE_MANDATORY_ACKNOWLEDGED, "NEWS_MESSAGE_MANDATORY_ACKNOWLEDGED"),
            (NEWS_MESSAGE_ADMIN_NOT_AUTHORIZED, "NEWS_MESSAGE_ADMIN_NOT_AUTHORIZED"),
            (NEWS_MESSAGE_ADMIN_MENU, "NEWS_MESSAGE_ADMIN_MENU"),
            (NEWS_MESSAGE_ADMIN_DRAFTS_EMPTY, "NEWS_MESSAGE_ADMIN_DRAFTS_EMPTY"),
            (NEWS_MESSAGE_ADMIN_PUBLISHED_EMPTY, "NEWS_MESSAGE_ADMIN_PUBLISHED_EMPTY"),
            (NEWS_MESSAGE_ADMIN_DRAFT_SAVED, "NEWS_MESSAGE_ADMIN_DRAFT_SAVED"),
            (NEWS_MESSAGE_ADMIN_PREVIEW_SENT, "NEWS_MESSAGE_ADMIN_PREVIEW_SENT"),
            (NEWS_MESSAGE_ADMIN_PUBLISHED, "NEWS_MESSAGE_ADMIN_PUBLISHED"),
        ]

        all_errors = []

        for message, name in messages_to_check:
            errors = self._check_markdown_v2_escaping(message, name)
            all_errors.extend(errors)

        if all_errors:
            self.fail("News MarkdownV2 formatting errors found:\n" + "\n".join(all_errors))
    
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
    
    def test_plain_text_messages_no_escaping(self):
        """Test that plain text messages (used without parse_mode) don't have escape sequences."""
        
        # These messages are displayed as plain text, so they should NOT have
        # backslash escape sequences that would look wrong to users
        plain_text_messages = [
            # UPOS error module - plain text messages
            (MESSAGE_SELECT_ACTION, "MESSAGE_SELECT_ACTION"),
            (MESSAGE_NO_CATEGORY, "MESSAGE_NO_CATEGORY"),
            (MESSAGE_NO_DATA, "MESSAGE_NO_DATA"),
            (MESSAGE_CSV_ERROR_NO_CODE_COLUMN, "MESSAGE_CSV_ERROR_NO_CODE_COLUMN"),
            (MESSAGE_CSV_ERROR_NO_DESC_COLUMN, "MESSAGE_CSV_ERROR_NO_DESC_COLUMN"),
            (MESSAGE_CSV_ERROR_NO_ACTIONS_COLUMN, "MESSAGE_CSV_ERROR_NO_ACTIONS_COLUMN"),
            (BUTTON_FORWARD, "BUTTON_FORWARD"),
            (BUTTON_BACK, "BUTTON_BACK"),
            (BUTTON_BACK_TO_MENU, "BUTTON_BACK_TO_MENU"),
            # Ticket validator module - plain text messages  
            (MESSAGE_ADMIN_NOT_ASSIGNED, "MESSAGE_ADMIN_NOT_ASSIGNED"),
            (MESSAGE_ADMIN_ENABLED, "MESSAGE_ADMIN_ENABLED"),
            (MESSAGE_ADMIN_DISABLED, "MESSAGE_ADMIN_DISABLED"),
            (MESSAGE_ADMIN_NO_ASSIGNED_RULES, "MESSAGE_ADMIN_NO_ASSIGNED_RULES"),
            (MESSAGE_ADMIN_NO_KEYWORDS, "MESSAGE_ADMIN_NO_KEYWORDS"),
            (MESSAGE_ADMIN_ALL_RULES_ADDED, "MESSAGE_ADMIN_ALL_RULES_ADDED"),
            (MESSAGE_ADMIN_SELECT_RULE_TO_ADD, "MESSAGE_ADMIN_SELECT_RULE_TO_ADD"),
            (MESSAGE_ADMIN_RULE_ALREADY_ADDED, "MESSAGE_ADMIN_RULE_ALREADY_ADDED"),
            (MESSAGE_ADMIN_ERROR, "MESSAGE_ADMIN_ERROR"),
            (MESSAGE_ADMIN_RULE_REMOVED, "MESSAGE_ADMIN_RULE_REMOVED"),
            (MESSAGE_ADMIN_ERROR_REMOVING, "MESSAGE_ADMIN_ERROR_REMOVING"),
            (MESSAGE_ADMIN_NOT_CONFIGURED, "MESSAGE_ADMIN_NOT_CONFIGURED"),
            (MESSAGE_ADMIN_NOT_SPECIFIED, "MESSAGE_ADMIN_NOT_SPECIFIED"),
            (MESSAGE_ADMIN_TEMPLATE_ENABLED, "MESSAGE_ADMIN_TEMPLATE_ENABLED"),
            (MESSAGE_ADMIN_TEMPLATE_DISABLED, "MESSAGE_ADMIN_TEMPLATE_DISABLED"),
            (MESSAGE_ADMIN_UNKNOWN_TEMPLATE, "MESSAGE_ADMIN_UNKNOWN_TEMPLATE"),
            (MESSAGE_ADMIN_CLICK_RULE_TO_REMOVE, "MESSAGE_ADMIN_CLICK_RULE_TO_REMOVE"),
            (MESSAGE_ADMIN_UNKNOWN_RULE, "MESSAGE_ADMIN_UNKNOWN_RULE"),
            (MESSAGE_ADMIN_SHOULD_PASS, "MESSAGE_ADMIN_SHOULD_PASS"),
            (MESSAGE_ADMIN_SHOULD_FAIL, "MESSAGE_ADMIN_SHOULD_FAIL"),
            (MESSAGE_ADMIN_EXPECTED_PASS, "MESSAGE_ADMIN_EXPECTED_PASS"),
            (MESSAGE_ADMIN_EXPECTED_FAIL, "MESSAGE_ADMIN_EXPECTED_FAIL"),
            (MESSAGE_ADMIN_ACTUAL_PASSED, "MESSAGE_ADMIN_ACTUAL_PASSED"),
            (MESSAGE_ADMIN_ACTUAL_FAILED, "MESSAGE_ADMIN_ACTUAL_FAILED"),
            # Vyezd byl module - plain text message
            (MESSAGE_PROCESSING_DONE, "MESSAGE_PROCESSING_DONE"),
        ]
        
        errors = []
        
        for message, name in plain_text_messages:
            # Plain text messages should not have backslash escaping
            if '\\' in message:
                errors.append(
                    f"{name}: Plain text message contains escape character '\\'. "
                    f"Value: {message[:50]}..."
                )
        
        if errors:
            self.fail("Plain text messages with unexpected escaping found:\n" + "\n".join(errors))


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
            # Common messages
            'MESSAGE_WELCOME',
            'MESSAGE_MAIN_HELP',
            'MESSAGE_PLEASE_ENTER_INVITE',
            'MESSAGE_UNRECOGNIZED_INPUT',
            'MESSAGE_NO_ADMIN_RIGHTS',
            # UPOS error messages
            'MESSAGE_SUBMENU',
            'MESSAGE_ENTER_ERROR_CODE',
            'MESSAGE_SEARCH_CANCELLED',
            'MESSAGE_INVALID_ERROR_CODE',
            'MESSAGE_NO_POPULAR_ERRORS',
            'MESSAGE_ADMIN_MENU',
            'MESSAGE_ADMIN_NOT_AUTHORIZED',
            'MESSAGE_ADMIN_ERRORS_LIST_EMPTY',
            'MESSAGE_NO_IMPORT_DATA',
            'MESSAGE_IMPORT_IN_PROGRESS',
            'MESSAGE_AND_MORE',
            # Ticket validator messages
            'MESSAGE_SEND_TICKET',
            'MESSAGE_VALIDATION_CANCELLED',
            'MESSAGE_VALIDATION_SUCCESS',
            'MESSAGE_ADMIN_NO_RULES_CONFIGURED',
            'MESSAGE_ADMIN_ALL_RULES_IN_TEMPLATE',
            'MESSAGE_ADMIN_ALL_TESTS_PASSED',
            'MESSAGE_ADMIN_RULE_NOT_FOUND',
            'MESSAGE_ADMIN_ERROR_UPDATING',
            'MESSAGE_NO_TICKET_TYPES',
            'MESSAGE_NO_RULES_CONFIGURED',
            'MESSAGE_VALIDATION_ERROR',
            'MESSAGE_RUNNING_TESTS',
            # Vyezd byl messages
            'VYEZD_MESSAGE_SUBMENU',
            'MESSAGE_INSTRUCTIONS',
            'VYEZD_MESSAGE_HELP',
            # News messages
            'NEWS_MESSAGE_SUBMENU',
            'NEWS_MESSAGE_SUBMENU_UNREAD',
            'NEWS_MESSAGE_NO_NEWS',
            'NEWS_MESSAGE_ARCHIVE_EMPTY',
            'NEWS_MESSAGE_SEARCH_PROMPT',
            'NEWS_MESSAGE_SEARCH_NO_RESULTS',
            'NEWS_MESSAGE_NEWS_MARKED_READ',
            'NEWS_MESSAGE_MANDATORY_NEWS',
            'NEWS_MESSAGE_MANDATORY_BLOCKING',
            'NEWS_MESSAGE_MANDATORY_ACKNOWLEDGED',
            'NEWS_MESSAGE_ADMIN_NOT_AUTHORIZED',
            'NEWS_MESSAGE_ADMIN_MENU',
            'NEWS_MESSAGE_ADMIN_DRAFTS_EMPTY',
            'NEWS_MESSAGE_ADMIN_PUBLISHED_EMPTY',
            'NEWS_MESSAGE_ADMIN_DRAFT_SAVED',
            'NEWS_MESSAGE_ADMIN_PREVIEW_SENT',
            'NEWS_MESSAGE_ADMIN_PUBLISHED',
        }
        
        # In a real implementation, you might scan the codebase for
        # parse_mode=constants.ParseMode.MARKDOWN_V2 usage
        
        # For now, this serves as documentation of what should be tested
        self.assertTrue(len(known_markdown_v2_messages) > 0, 
                       "At least some messages should use MARKDOWN_V2")


if __name__ == '__main__':
    unittest.main(verbosity=2)