#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify Telegram MarkdownV2 formatting for negative keywords.
This simulates what would be sent to Telegram bot in debug mode.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.sbs_helper_telegram_bot.ticket_validator.validators import (
    TicketType,
    detect_ticket_type
)


def _escape_md(text: str) -> str:
    """Escape special characters for MarkdownV2 - copied from ticket_validator_bot_part.py"""
    if text is None:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = str(text).replace(char, f'\\{char}')
    return text


def format_debug_info_for_telegram(debug_info) -> str:
    """Format DetectionDebugInfo for Telegram message - copied from ticket_validator_bot_part.py"""
    lines = []
    lines.append("🔍 *DEBUG: Определение типа заявки*")
    lines.append("")
    
    if debug_info.detected_type:
        lines.append(f"✅ *Определён тип:* {_escape_md(debug_info.detected_type.type_name)}")
    else:
        lines.append("❌ *Тип не определён*")
    
    lines.append(f"📊 Оценено типов: {debug_info.total_types_evaluated}")
    lines.append("")
    lines.append("*Результаты по типам:*")
    
    # Sort by score descending
    sorted_scores = sorted(debug_info.all_scores, key=lambda x: x.total_score, reverse=True)
    
    for score_info in sorted_scores:
        type_name = _escape_md(score_info.ticket_type.type_name)
        # Escape decimal points and minus signs in numeric values
        total_score_str = str(score_info.total_score).replace('.', '\\.').replace('-', '\\-')
        match_pct_str = f"{score_info.match_percentage:.1f}".replace('.', '\\.')
        
        lines.append("")
        lines.append(f"📋 *{type_name}*")
        lines.append(f"   Счёт: {total_score_str}")
        lines.append(f"   Совпало: {score_info.matched_keywords_count}/{score_info.total_keywords_count} \\({match_pct_str}%\\)")
        
        if score_info.keyword_matches:
            lines.append("   Ключевые слова:")
            for match in score_info.keyword_matches[:5]:  # Limit to 5 keywords
                keyword = _escape_md(match.keyword)
                weight_str = str(match.weight).replace('.', '\\.')
                score_str = str(match.weighted_score).replace('.', '\\.').replace('-', '\\-')
                # Use different indicator for negative keywords
                indicator = "⊖" if match.is_negative else "⊕"
                lines.append(f"     {indicator} '{keyword}': {match.count}x \\(вес: {weight_str}, счёт: {score_str}\\)")
            if len(score_info.keyword_matches) > 5:
                lines.append(f"     _\\.\\.\\.и ещё {len(score_info.keyword_matches) - 5}_")
    
    return "\n".join(lines)


def test_telegram_markdown_formatting():
    """Test that negative keywords don't break Telegram MarkdownV2 formatting."""
    
    print("Testing Telegram MarkdownV2 formatting with negative keywords...")
    print("=" * 80)
    
    # Define ticket types with negative keywords
    ticket_types = [
        TicketType(
            id=1,
            type_name="Установка оборудования",
            description="Новая установка",
            detection_keywords=["установка", "монтаж", "-ремонт", "-замена"]
        ),
        TicketType(
            id=2,
            type_name="Ремонт",
            description="Ремонт оборудования",
            detection_keywords=["ремонт", "поломка", "-установка"]
        ),
    ]
    
    # Test case with both positive and negative keywords
    ticket_text = "Установка и монтаж нового оборудования после ремонта"
    
    print(f"\nТестовый текст: {ticket_text}")
    print("\n" + "=" * 80)
    
    # Detect with debug mode
    detected, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=True)
    
    # Format for Telegram
    telegram_message = format_debug_info_for_telegram(debug_info)
    
    print("\nФорматированное сообщение для Telegram (MarkdownV2):")
    print("-" * 80)
    print(telegram_message)
    print("-" * 80)
    
    # Check for unescaped minus signs
    lines = telegram_message.split('\n')
    has_issues = False
    
    for i, line in enumerate(lines, 1):
        # Look for unescaped minus signs (minus not preceded by backslash)
        # But ignore escaped ones like \-
        if '-' in line and '\\-' not in line.replace('\\\\-', ''):
            # Check if it's really unescaped
            idx = line.find('-')
            while idx != -1:
                if idx == 0 or line[idx-1] != '\\':
                    print(f"\n⚠️  WARNING: Line {i} has unescaped minus sign:")
                    print(f"   {line}")
                    has_issues = True
                    break
                idx = line.find('-', idx + 1)
    
    if not has_issues:
        print("\n✅ SUCCESS: All minus signs are properly escaped!")
        print("   The message should not cause 'character \"-\" is reserved' error")
    else:
        print("\n❌ FAILED: Found unescaped minus signs!")
        print("   This would cause Telegram API error")
    
    print("\n" + "=" * 80)
    
    # Show what the indicators look like
    print("\nИндикаторы в сообщении:")
    print("  ⊕ = Позитивное ключевое слово (увеличивает счёт)")
    print("  ⊖ = Негативное ключевое слово (уменьшает счёт)")
    
    return not has_issues


if __name__ == "__main__":
    success = test_telegram_markdown_formatting()
    sys.exit(0 if success else 1)
