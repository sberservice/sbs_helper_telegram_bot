#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demonstration of negative keywords feature for ticket type detection.

This script shows how negative keywords (prefixed with minus sign) 
can improve ticket classification accuracy.
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


def demonstrate_negative_keywords():
    """Demonstrate the negative keywords feature with examples."""
    
    print("NEGATIVE KEYWORDS DEMONSTRATION")
    print_separator()
    
    # Define ticket types with negative keywords
    ticket_types = [
        TicketType(
            id=1,
            type_name="Установка оборудования",
            description="Новая установка",
            detection_keywords=["установка", "монтаж", "новое", "-ремонт", "-замена"]
        ),
        TicketType(
            id=2,
            type_name="Ремонт",
            description="Ремонт оборудования",
            detection_keywords=["ремонт", "поломка", "сломалось", "-установка"]
        ),
        TicketType(
            id=3,
            type_name="Замена оборудования",
            description="Замена существующего оборудования",
            detection_keywords=["замена", "заменить", "-установка", "-ремонт"]
        ),
    ]
    
    # Test cases
    test_cases = [
        {
            "text": "Нужна установка нового оборудования",
            "expected": "Установка оборудования",
            "description": "Clear installation request"
        },
        {
            "text": "Установка и монтаж нового оборудования после ремонта старого",
            "expected": "Установка оборудования",
            "description": "Multiple installation keywords outweigh single negative keyword"
        },
        {
            "text": "Замена кассы на новую",
            "expected": "Замена оборудования",
            "description": "Replacement request"
        },
        {
            "text": "Касса сломалась, нужен ремонт поломки",
            "expected": "Ремонт",
            "description": "Multiple repair keywords"
        },
        {
            "text": "Замена заменить сломанного оборудования",
            "expected": "Замена оборудования",
            "description": "Multiple replacement keywords"
        },
    ]
    
    # Run test cases
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test Case {i}: {test_case['description']}")
        print(f"Text: \"{test_case['text']}\"")
        print(f"Expected: {test_case['expected']}")
        
        detected, debug_info = detect_ticket_type(
            test_case['text'], 
            ticket_types,
            debug=True
        )
        
        if detected:
            print(f"✓ Detected: {detected.type_name}")
            
            # Show scores
            print("\nScores:")
            for score_info in sorted(debug_info.all_scores, 
                                    key=lambda x: x.total_score, 
                                    reverse=True):
                print(f"  {score_info.ticket_type.type_name}: {score_info.total_score:.1f}")
                
                if score_info.keyword_matches:
                    for match in score_info.keyword_matches:
                        sign = "-" if match.is_negative else "+"
                        print(f"    {sign} '{match.keyword}': {match.count}x (score: {match.weighted_score:.1f})")
        else:
            print("✗ No type detected")
        
        # Check if result matches expectation
        matches = detected and detected.type_name == test_case['expected']
        status = "✓ PASS" if matches else "✗ FAIL"
        print(f"\n{status}")
        print_separator()


def demonstrate_with_weights():
    """Demonstrate negative keywords with custom weights."""
    
    print("NEGATIVE KEYWORDS WITH CUSTOM WEIGHTS")
    print_separator()
    
    ticket_types = [
        TicketType(
            id=1,
            type_name="Установка",
            description="Installation",
            detection_keywords=["установка", "-ремонт"]
        ),
        TicketType(
            id=2,
            type_name="Ремонт",
            description="Repair",
            detection_keywords=["ремонт"]
        ),
    ]
    
    ticket_text = "Установка после ремонта"
    
    # Without custom weights
    print("Without custom weights:")
    detected1, debug1 = detect_ticket_type(ticket_text, ticket_types, debug=True)
    print(f"Detected: {detected1.type_name if detected1 else 'None'}")
    for score in debug1.all_scores:
        print(f"  {score.ticket_type.type_name}: {score.total_score:.1f}")
    
    print()
    
    # With custom weight on negative keyword
    print("With -ремонт weight = 3.0:")
    detected2, debug2 = detect_ticket_type(
        ticket_text, 
        ticket_types, 
        debug=True,
        keyword_weights={"-ремонт": 3.0}
    )
    print(f"Detected: {detected2.type_name if detected2 else 'None'}")
    for score in debug2.all_scores:
        print(f"  {score.ticket_type.type_name}: {score.total_score:.1f}")
    
    print_separator()


if __name__ == "__main__":
    demonstrate_negative_keywords()
    demonstrate_with_weights()
    
    print("\n✓ Negative keywords feature demonstration complete!")
