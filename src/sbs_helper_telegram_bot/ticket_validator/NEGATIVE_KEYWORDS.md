# Negative Keywords Feature

## Overview

The ticket validator now supports **negative keywords** that lower the score when determining the ticket type. This helps to more accurately classify tickets by penalizing matches that contain words which should not be associated with a particular ticket type.

## How It Works

### Basic Usage

Simply prefix a keyword with a minus sign (`-`) to make it a negative keyword.

**Example:**
```json
["установка", "монтаж", "-ремонт"]
```

In this example:
- `установка` and `монтаж` are positive keywords (add to the score)
- `-ремонт` is a negative keyword (subtracts from the score)

### Scoring Logic

When detecting ticket types:
- Each **positive keyword** found in the text adds to the score (default +1 per occurrence)
- Each **negative keyword** found in the text subtracts from the score (default -1 per occurrence)
- The ticket type with the highest total score is selected

### Example Scenario

**Ticket Types:**
```json
{
  "id": 1,
  "type_name": "Установка оборудования",
  "detection_keywords": ["установка", "монтаж", "-ремонт", "-замена"]
}
{
  "id": 2,
  "type_name": "Ремонт оборудования",
  "detection_keywords": ["ремонт", "поломка"]
}
```

**Ticket Text:** "Установка нового оборудования, а не ремонт"

**Score Calculation:**
- Type 1 (Установка): `установка` (+1) + `-ремонт` (-1) = **0**
- Type 2 (Ремонт): `ремонт` (+1) = **1**

**Result:** Type 2 (Ремонт) is detected because it has a higher score.

## Custom Weights

Negative keywords also work with custom weights:

```python
keyword_weights = {
    "-ремонт": 2.0  # Negative keyword with doubled weight
}
```

This would give `-ремонт` a score of **-2.0** instead of **-1.0** when found.

## Best Practices

### 1. Use Negative Keywords to Disambiguate Similar Types

If two ticket types share common words but have distinct purposes:

```json
// Новая установка
["установка", "новое", "-замена", "-перенос"]

// Замена оборудования  
["замена", "заменить", "-установка"]

// Перенос оборудования
["перенос", "переместить", "-установка"]
```

### 2. Filter Out Generic Terms

If a keyword appears in many contexts but should exclude certain ticket types:

```json
// Техническое обслуживание
["обслуживание", "профилактика", "-поломка", "-ремонт"]

// Ремонт
["ремонт", "поломка", "-профилактика"]
```

### 3. Prevent False Positives

Use negative keywords to prevent classification when contradictory terms appear:

```json
// Выезд специалиста
["выезд", "диагностика", "-удаленно", "-дистанционно"]
```

## Database Storage

Negative keywords are stored in the same JSON array as positive keywords in the `detection_keywords` column:

```sql
UPDATE ticket_types 
SET detection_keywords = '["установка", "монтаж", "-ремонт", "-замена"]'
WHERE id = 1;
```

## Debug Information

When using debug mode, negative keywords are displayed with a minus sign:

```
SCORES BY TICKET TYPE:
1. Установка оборудования (Score: -1.0)
   Keywords matched: 1/4 (25.0%)
   Matched keywords:
     + 'установка': found 1x (weight: 1.0, score: 1.0)
     - 'ремонт': found 1x (weight: 1.0, score: -1.0)
```

The `+` prefix indicates positive keywords, and the `-` prefix indicates negative keywords.

## API Reference

### KeywordMatch Class

```python
@dataclass
class KeywordMatch:
    keyword: str          # The keyword (without minus sign)
    count: int           # Number of times found in text
    weight: float = 1.0  # Weight multiplier
    is_negative: bool = False  # Whether this is a negative keyword
    
    @property
    def weighted_score(self) -> float:
        # Returns negative value if is_negative=True
        score = self.count * self.weight
        return -score if self.is_negative else score
```

### Detection Function

```python
def detect_ticket_type(
    ticket_text: str, 
    ticket_types: List[TicketType],
    debug: bool = False,
    keyword_weights: Optional[Dict[str, float]] = None
) -> tuple[Optional[TicketType], Optional[DetectionDebugInfo]]:
    """
    Detect ticket type from text based on keywords.
    
    Negative keywords (prefixed with -) will lower the score.
    """
```

## Migration Guide

To add negative keywords to existing ticket types:

```sql
-- Add negative keywords to prevent misclassification
UPDATE ticket_types 
SET detection_keywords = JSON_ARRAY_APPEND(
    detection_keywords, 
    '$', 
    '-нежелательное_слово'
)
WHERE type_name = 'Установка оборудования';
```

Or replace the entire keywords array:

```sql
UPDATE ticket_types 
SET detection_keywords = '["ключевое", "слово", "-исключение"]'
WHERE type_name = 'Установка оборудования';
```

## Testing

The feature includes comprehensive unit tests in [test_ticket_validator.py](../../../tests/test_ticket_validator.py):

- `test_negative_keywords_lower_score` - Basic negative keyword functionality
- `test_negative_keywords_with_weights` - Custom weights for negative keywords
- `test_negative_keywords_debug_info` - Debug output verification
- `test_negative_keywords_not_counted_in_matched` - Match counting behavior
- `test_multiple_negative_keywords` - Multiple negative keywords per type

Run tests with:
```bash
python -m pytest tests/test_ticket_validator.py::TestTicketTypeDetection -v
```
