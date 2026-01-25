#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demonstration of keyword weights feature for ticket type detection.

This script shows how different keywords can have different weights
to improve ticket classification accuracy.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.sbs_helper_telegram_bot.ticket_validator.validators import (
    TicketType,
    detect_ticket_type
)


def print_separator():
    print("\n" + "="*80 + "\n")


def demonstrate_keyword_weights():
    """Demonstrate the keyword weights feature with examples."""
    
    print("KEYWORD WEIGHTS DEMONSTRATION")
    print_separator()
    
    print("Keyword weights allow certain keywords to have more influence on detection.")
    print("A keyword with weight 2.0 contributes twice as much to the score as weight 1.0")
    print()
    
    # Define ticket types WITHOUT weights (baseline)
    ticket_types_no_weights = [
        TicketType(
            id=1,
            type_name="Установка ККТ",
            description="Установка кассовой техники",
            detection_keywords=["установка", "монтаж", "ккт", "касса"]
        ),
        TicketType(
            id=2,
            type_name="Ремонт ККТ",
            description="Ремонт кассовой техники",
            detection_keywords=["ремонт", "сломалось", "ккт", "касса"]
        ),
    ]
    
    # Define ticket types WITH weights
    ticket_types_with_weights = [
        TicketType(
            id=1,
            type_name="Установка ККТ",
            description="Установка кассовой техники",
            detection_keywords=["установка", "монтаж", "ккт", "касса"],
            keyword_weights={
                "установка": 3.0,  # Strong indicator for installation
                "монтаж": 2.5,     # Also strong indicator
                "ккт": 1.0,        # Common word, normal weight
                "касса": 1.0       # Common word, normal weight
            }
        ),
        TicketType(
            id=2,
            type_name="Ремонт ККТ",
            description="Ремонт кассовой техники",
            detection_keywords=["ремонт", "сломалось", "ккт", "касса"],
            keyword_weights={
                "ремонт": 3.0,     # Strong indicator for repair
                "сломалось": 2.5,  # Also strong indicator
                "ккт": 1.0,        # Common word, normal weight
                "касса": 1.0       # Common word, normal weight
            }
        ),
    ]
    
    # Test case where common words might cause wrong detection
    test_text = "Касса ККТ установка после ремонта"
    
    print(f"Test text: \"{test_text}\"")
    print_separator()
    
    # WITHOUT weights
    print("1. WITHOUT KEYWORD WEIGHTS (all keywords weight = 1.0):")
    detected1, debug1 = detect_ticket_type(test_text, ticket_types_no_weights, debug=True)
    print(f"   Detected: {detected1.type_name if detected1 else 'None'}")
    print("\n   Scores:")
    for score_info in sorted(debug1.all_scores, key=lambda x: x.total_score, reverse=True):
        print(f"   - {score_info.ticket_type.type_name}: {score_info.total_score:.1f}")
        for match in score_info.keyword_matches:
            print(f"       '{match.keyword}': {match.count}x × {match.weight} = {match.weighted_score:.1f}")
    
    print_separator()
    
    # WITH weights stored in TicketType
    print("2. WITH KEYWORD WEIGHTS (stored in TicketType.keyword_weights):")
    detected2, debug2 = detect_ticket_type(test_text, ticket_types_with_weights, debug=True)
    print(f"   Detected: {detected2.type_name if detected2 else 'None'}")
    print("\n   Scores:")
    for score_info in sorted(debug2.all_scores, key=lambda x: x.total_score, reverse=True):
        print(f"   - {score_info.ticket_type.type_name}: {score_info.total_score:.1f}")
        for match in score_info.keyword_matches:
            print(f"       '{match.keyword}': {match.count}x × {match.weight} = {match.weighted_score:.1f}")
    
    print_separator()


def demonstrate_weight_override():
    """Demonstrate overriding TicketType weights with parameter weights."""
    
    print("WEIGHT OVERRIDE DEMONSTRATION")
    print_separator()
    
    print("Weights passed via keyword_weights parameter override TicketType weights")
    print()
    
    ticket_type = TicketType(
        id=1,
        type_name="Установка",
        description="Installation",
        detection_keywords=["установка", "монтаж"],
        keyword_weights={"установка": 2.0, "монтаж": 1.5}  # Type's own weights
    )
    
    test_text = "установка монтаж"
    
    # Using TicketType's weights
    print("1. Using TicketType's weights:")
    _, debug1 = detect_ticket_type(test_text, [ticket_type], debug=True)
    for match in debug1.all_scores[0].keyword_matches:
        print(f"   '{match.keyword}': weight = {match.weight}")
    print(f"   Total: {debug1.all_scores[0].total_score:.1f}")
    
    print()
    
    # Overriding with parameter weights
    print("2. Overriding with keyword_weights parameter:")
    _, debug2 = detect_ticket_type(
        test_text, 
        [ticket_type], 
        debug=True,
        keyword_weights={"установка": 5.0}  # Override only "установка"
    )
    for match in debug2.all_scores[0].keyword_matches:
        print(f"   '{match.keyword}': weight = {match.weight}")
    print(f"   Total: {debug2.all_scores[0].total_score:.1f}")
    
    print_separator()


def demonstrate_negative_with_weights():
    """Demonstrate negative keywords combined with weights."""
    
    print("NEGATIVE KEYWORDS WITH WEIGHTS")
    print_separator()
    
    print("Negative keywords can also have weights.")
    print("Higher weight = stronger penalty for negative keywords.")
    print()
    
    ticket_types = [
        TicketType(
            id=1,
            type_name="Установка",
            description="New installation only",
            detection_keywords=["установка", "новая", "-ремонт"],
            keyword_weights={
                "установка": 2.0,
                "новая": 1.5,
                "-ремонт": 3.0  # Strong penalty if "ремонт" is mentioned
            }
        ),
        TicketType(
            id=2,
            type_name="Ремонт",
            description="Repair",
            detection_keywords=["ремонт", "-установка"],
            keyword_weights={
                "ремонт": 2.0,
                "-установка": 1.0  # Mild penalty
            }
        ),
    ]
    
    test_cases = [
        "Новая установка оборудования",
        "Установка после ремонта",
        "Ремонт и установка",
    ]
    
    for text in test_cases:
        print(f"Text: \"{text}\"")
        detected, debug = detect_ticket_type(text, ticket_types, debug=True)
        print(f"Detected: {detected.type_name if detected else 'None'}")
        
        print("Scores:")
        for score_info in sorted(debug.all_scores, key=lambda x: x.total_score, reverse=True):
            print(f"  {score_info.ticket_type.type_name}: {score_info.total_score:.1f}")
            for match in score_info.keyword_matches:
                sign = "-" if match.is_negative else "+"
                print(f"    {sign} '{match.keyword}': {match.count}x × {match.weight} = {match.weighted_score:.1f}")
        print()


def demonstrate_get_keyword_weight():
    """Demonstrate the get_keyword_weight helper method."""
    
    print_separator()
    print("USING get_keyword_weight() METHOD")
    print_separator()
    
    ticket_type = TicketType(
        id=1,
        type_name="Test",
        description="Test type",
        detection_keywords=["установка", "монтаж", "ккт"],
        keyword_weights={
            "установка": 3.0,
            "монтаж": 2.5
            # "ккт" not specified - will default to 1.0
        }
    )
    
    keywords_to_check = ["установка", "монтаж", "ккт", "unknown"]
    
    print("Getting weights for keywords:")
    for kw in keywords_to_check:
        weight = ticket_type.get_keyword_weight(kw)
        print(f"  '{kw}': {weight}")
    
    print_separator()


if __name__ == "__main__":
    demonstrate_keyword_weights()
    demonstrate_weight_override()
    demonstrate_negative_with_weights()
    demonstrate_get_keyword_weight()
    
    print("\n✓ Keyword weights feature demonstration complete!")
