# Negative Keywords Feature - Implementation Summary

## What Was Implemented

I've successfully added support for **negative keywords** that lower the score when determining ticket types. This feature allows keywords prefixed with a minus sign (`-`) to reduce the classification score, making ticket type detection more accurate.

## Changes Made

### 1. Core Implementation ([validators.py](src/sbs_helper_telegram_bot/ticket_validator/validators.py))

#### Updated `KeywordMatch` Class
- Added `is_negative: bool` field to track if a keyword is negative
- Modified `weighted_score` property to return negative values for negative keywords

```python
@dataclass
class KeywordMatch:
    keyword: str
    count: int
    weight: float = 1.0
    is_negative: bool = False
    
    @property
    def weighted_score(self) -> float:
        score = self.count * self.weight
        return -score if self.is_negative else score
```

#### Updated `detect_ticket_type` Function
- Detects keywords starting with `-` as negative keywords
- Removes the minus sign before matching in text
- Applies negative scoring for matches of negative keywords
- Negative keywords don't count towards `matched_keywords_count`
- Supports custom weights for negative keywords

### 2. Tests ([tests/test_ticket_validator.py](tests/test_ticket_validator.py))

Added 5 comprehensive test cases:
- `test_negative_keywords_lower_score` - Basic functionality
- `test_negative_keywords_with_weights` - Custom weight support
- `test_negative_keywords_debug_info` - Debug output verification
- `test_negative_keywords_not_counted_in_matched` - Match counting behavior
- `test_multiple_negative_keywords` - Multiple negative keywords per type

**All 72 tests pass ✓**

### 3. Documentation

#### [NEGATIVE_KEYWORDS.md](src/sbs_helper_telegram_bot/ticket_validator/NEGATIVE_KEYWORDS.md)
Comprehensive guide including:
- How negative keywords work
- Scoring logic explanation
- Usage examples
- Best practices
- API reference
- Migration guide

#### [example_negative_keywords.sql](scripts/example_negative_keywords.sql)
SQL script showing how to add negative keywords to existing ticket types:

```sql
UPDATE ticket_types 
SET detection_keywords = '["установка", "монтаж", "-ремонт", "-замена"]'
WHERE type_name = 'Установка оборудования';
```

#### [demo_negative_keywords.py](examples/demo_negative_keywords.py)
Working demonstration script showing the feature in action

## How It Works

### Syntax
Simply prefix any keyword with a minus sign:
```json
["установка", "монтаж", "-ремонт", "-замена"]
```

### Scoring
- **Positive keywords**: Add to score (default +1 per occurrence)
- **Negative keywords**: Subtract from score (default -1 per occurrence)
- Final score determines which ticket type matches best
- Only ticket types with score > 0 are considered

### Example

**Ticket Types:**
- Installation: `["установка", "монтаж", "-ремонт"]`
- Repair: `["ремонт", "поломка"]`

**Text:** "Установка и монтаж нового оборудования после ремонта старого"

**Scores:**
- Installation: `установка(+1) + монтаж(+1) + -ремонт(-1) = +1`
- Repair: `ремонт(+1) = +1`

In case of tie, first positive score wins.

## Use Cases

### 1. Disambiguation
Prevent false positives when similar words appear in different contexts:
```json
// New installation
["установка", "новое", "-замена", "-перенос"]

// Replacement
["замена", "заменить", "-установка"]
```

### 2. Context Filtering
Exclude specific scenarios:
```json
// Field service
["выезд", "на месте", "-удаленно", "-дистанционно"]

// Remote support
["удаленно", "дистанционно", "-выезд"]
```

### 3. Quality Control
Prevent classification when contradictory terms appear:
```json
// Maintenance
["обслуживание", "профилактика", "-поломка", "-ремонт"]
```

## Benefits

1. **Higher Accuracy**: Reduces false positive classifications
2. **Better Context Understanding**: Handles "not X" scenarios properly
3. **Flexible Configuration**: Works with existing keyword system
4. **Custom Weights**: Can emphasize exclusions more strongly
5. **No Database Schema Changes**: Works with current JSON storage

## Testing

Run all tests:
```bash
python -m pytest tests/test_ticket_validator.py -v
```

Run demonstration:
```bash
python3 examples/demo_negative_keywords.py
```

## Backward Compatibility

✓ Fully backward compatible
- Existing keywords without `-` prefix work exactly as before
- No database migration required
- Existing ticket types continue to work unchanged

## Next Steps (Optional)

1. Add negative keywords to production ticket types based on real-world classification errors
2. Monitor effectiveness and adjust weights as needed
3. Consider adding admin UI for easier negative keyword management
4. Add analytics to track how often negative keywords change classification outcomes
