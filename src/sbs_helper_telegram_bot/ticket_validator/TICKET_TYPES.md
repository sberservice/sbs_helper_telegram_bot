# Ticket Types and Smart Validation

## Overview

The ticket validator now supports **different ticket types** (templates), where each type has its own set of validation rules. The bot can automatically detect which type of ticket the user is submitting based on keywords and apply only the relevant validation rules.

## How It Works

### 1. Ticket Type Detection

When a user submits a ticket, the bot:
1. Loads all active ticket types from the database
2. Scores each type based on keyword matches in the ticket text
3. Selects the ticket type with the highest score
4. Loads validation rules specific to that ticket type
5. Validates the ticket using only relevant rules

### 2. Keyword-Based Detection

Each ticket type has a list of detection keywords stored as JSON:

```json
["установка", "монтаж", "новое оборудование", "подключение"]
```

The bot counts occurrences of these keywords and picks the type with the most matches.

### 3. Rule Mapping

Validation rules are mapped to ticket types through the `ticket_validator_ticket_type_rules` junction table, creating a many-to-many relationship:
- One rule can be used in multiple ticket types
- One ticket type can have multiple rules

## Database Schema

### New Tables

#### `ticket_validator_ticket_types`
Stores different types of service requests.

| Column | Type | Description |
|--------|------|-------------|
| id | bigint | Primary key |
| type_name | varchar(255) | Name of ticket type |
| description | text | Description |
| detection_keywords | text | JSON array of keywords |
| active | tinyint(1) | Active flag |
| created_timestamp | bigint | Creation time |

#### `ticket_validator_ticket_type_rules`
Junction table mapping rules to ticket types.

| Column | Type | Description |
|--------|------|-------------|
| id | bigint | Primary key |
| ticket_type_id | bigint | FK to ticket_types |
| validation_rule_id | bigint | FK to validation_rules |
| created_timestamp | bigint | Creation time |

#### `validation_history`
Includes `ticket_type_id` column to track which type was detected.

## Setup

### 1. Create Database Schema

```bash
mysql -u user -p database < schema.sql
```

### 2. Load Ticket Types

```bash
mysql -u user -p database < scripts/initial_ticket_types.sql
```

Default ticket types:
1. **Установка оборудования** - Installation of new equipment
2. **Техническое обслуживание** - Scheduled maintenance
3. **Ремонт** - Equipment repair
4. **Регистрация в ФНС** - Tax service registration
5. **Замена оборудования** - Equipment replacement

### 3. Map Rules to Ticket Types

```bash
# Create rule-to-type mappings
mysql -u user -p database < scripts/map_rules_to_ticket_types.sql
```

## Usage Examples

### Example 1: Installation Ticket

**User submits:**
```
Заявка на установку оборудования

Организация: ООО "Новая компания"
ИНН: 1234567890
Система налогообложения: УСН

Контактное лицо: Петров П.П.
Телефон: +7 (999) 123-45-67

Адрес установки: г. Москва, ул. Примерная, д. 1
Дата установки: 25.01.2026

Оборудование: АТОЛ 91Ф
Код активации: ABC123XYZ456
```

**Bot detects:** "Установка оборудования" (keywords: "установка оборудования")  
**Validation rules applied:**
- ✅ Система налогообложения
- ✅ ИНН
- ✅ Организация
- ✅ Контактное лицо
- ✅ Телефон
- ✅ Адрес установки
- ✅ Код активации
- ✅ Тип оборудования
- ✅ Дата

**Result:** ✅ Заявка прошла валидацию! (тип: _Установка оборудования_)

### Example 2: Maintenance Ticket

**User submits:**
```
Техническое обслуживание

Компания: ООО "Рога и Копыта"
ИНН: 9876543210
Налогообложение: ОСНО

ФИО: Иванов И.И.
Тел: 8 495 111-22-33

Оборудование: Меркурий 185Ф
Дата ТО: 30.01.2026
```

**Bot detects:** "Техническое обслуживание" (keywords: "техническое обслуживание", "ТО")  
**Validation rules applied:**
- ✅ Common rules (tax, INN, org, contact, phone)
- ✅ Equipment type
- ✅ Service date
- ❌ NO activation code required (not needed for maintenance)
- ❌ NO installation address required

**Result:** ✅ Заявка прошла валидацию! (тип: _Техническое обслуживание_)

### Example 3: Repair Ticket

**User submits:**
```
Ремонт кассы

Организация: ИП Сидоров
ИНН: 123456789012
УСН

Контакт: Сидоров С.С.
Телефон: +79991234567

Оборудование: АТОЛ 90Ф
Проблема: не печатает чеки
```

**Bot detects:** "Ремонт" (keywords: "ремонт", "проблема")  
**Validation rules applied:**
- ✅ Common rules only
- ✅ Equipment type
- ❌ NO activation code (not replacing)
- ❌ NO service date (urgent repair)
- ❌ NO address (repairing existing)

**Result:** ✅ Заявка прошла валидацию! (тип: _Ремонт_)

## API Changes

### validators.py

#### New: `TicketType` dataclass
```python
@dataclass
class TicketType:
    id: int
    type_name: str
    description: str
    detection_keywords: List[str]
    active: bool = True
```

#### New: `detect_ticket_type()` function
```python
def detect_ticket_type(ticket_text: str, ticket_types: List[TicketType]) -> Optional[TicketType]:
    """Detect ticket type from text based on keywords."""
```

#### Updated: `ValidationResult`
```python
@dataclass
class ValidationResult:
    # ... existing fields ...
    detected_ticket_type: Optional[TicketType] = None  # NEW
```

#### Updated: `validate_ticket()`
```python
def validate_ticket(ticket_text: str, rules: List[ValidationRule], 
                   detected_ticket_type: Optional[TicketType] = None) -> ValidationResult:
```

### validation_rules.py

#### New Functions
```python
def load_all_ticket_types() -> List[TicketType]:
    """Load all active ticket types from database."""

def load_ticket_type_by_id(ticket_type_id: int) -> Optional[TicketType]:
    """Load specific ticket type by ID."""
```

#### Updated: `load_rules_from_db()`
```python
def load_rules_from_db(ticket_type_id: Optional[int] = None) -> List[ValidationRule]:
    """Load rules for specific ticket type or all rules if type_id is None."""
```

#### Updated: `store_validation_result()`
```python
def store_validation_result(userid, ticket_text, is_valid, failed_rules, 
                           ticket_type_id: Optional[int] = None) -> int:
```

## Managing Ticket Types

### Add New Ticket Type

```sql
INSERT INTO ticket_types 
(type_name, description, detection_keywords, active, created_timestamp)
VALUES 
('Модернизация', 
 'Обновление программного обеспечения',
 '["модернизация", "обновление", "апгрейд", "ПО", "прошивка"]',
 1,
 UNIX_TIMESTAMP());
```

### Map Rules to New Type

```sql
-- Map common rules (1,3,5,6,7,10) + specific rules (8,9)
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id, created_timestamp)
SELECT 6, id, UNIX_TIMESTAMP()  -- 6 = new ticket type ID
FROM validation_rules 
WHERE id IN (1,3,5,6,7,8,9,10);
```

### Update Detection Keywords

```sql
UPDATE ticket_types 
SET detection_keywords = '["новые", "ключевые", "слова"]'
WHERE id = 1;
```

### Deactivate Ticket Type

```sql
UPDATE ticket_types SET active = 0 WHERE id = 3;
```

## Rule Reusability

Rules can be shared across multiple ticket types:

| Rule | Installation | Maintenance | Repair | Registration | Replacement |
|------|--------------|-------------|--------|--------------|-------------|
| Tax System | ✅ | ✅ | ✅ | ✅ | ✅ |
| INN | ✅ | ✅ | ✅ | ✅ | ✅ |
| Organization | ✅ | ✅ | ✅ | ✅ | ✅ |
| Contact Person | ✅ | ✅ | ✅ | ✅ | ✅ |
| Phone | ✅ | ✅ | ✅ | ✅ | ✅ |
| Activation Code | ✅ | ❌ | ❌ | ✅ | ✅ |
| Address | ✅ | ❌ | ❌ | ✅ | ✅ |
| Equipment | ✅ | ✅ | ✅ | ✅ | ✅ |
| Service Date | ✅ | ✅ | ❌ | ❌ | ✅ |

## Benefits

### For Users
- ✅ **Relevant validation only** - No irrelevant errors
- ✅ **Automatic detection** - No manual selection needed
- ✅ **Better error messages** - Context-aware feedback

### For Administrators
- ✅ **Flexible configuration** - Easy to add new ticket types
- ✅ **Rule reusability** - Share rules across types
- ✅ **Better analytics** - Track validation by ticket type

### For System
- ✅ **Scalability** - Easy to add new workflows
- ✅ **Maintainability** - Centralized rule management
- ✅ **Performance** - Fewer rules to validate per ticket

## Fallback Behavior

If no ticket type is detected (no keyword matches):
- Bot validates using **ALL active rules**
- No ticket type shown in response
- History records `ticket_type_id` as NULL

This ensures validation still works even for unusual tickets.

## Testing

### Test Ticket Type Detection

```python
from src.sbs_helper_telegram_bot.ticket_validator.validators import detect_ticket_type, TicketType

ticket_types = [
    TicketType(1, "Установка", "", ["установка", "монтаж"]),
    TicketType(2, "Ремонт", "", ["ремонт", "поломка"])
]

text1 = "Заявка на установку нового оборудования"
detected = detect_ticket_type(text1, ticket_types)
assert detected.id == 1  # Installation

text2 = "Ремонт сломанной кассы"
detected = detect_ticket_type(text2, ticket_types)
assert detected.id == 2  # Repair
```

### Test Rule Loading by Type

```python
from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import load_rules_from_db

# Load rules for ticket type 1 (Installation)
installation_rules = load_rules_from_db(ticket_type_id=1)
assert len(installation_rules) == 9  # Should have 9 rules

# Load rules for ticket type 2 (Maintenance)
maintenance_rules = load_rules_from_db(ticket_type_id=2)
assert len(maintenance_rules) == 7  # Should have 7 rules (no activation/address)

# Load all rules
all_rules = load_rules_from_db()
assert len(all_rules) == 10  # All 10 rules
```

## Future Enhancements

### 1. User-Selectable Types
Add inline keyboard for users to manually select ticket type:
```python
keyboard = [[InlineKeyboardButton(t.type_name, callback_data=f"type_{t.id}") 
             for t in ticket_types]]
```

### 2. Confidence Threshold
Only auto-detect if confidence is above threshold:
```python
if score >= MIN_CONFIDENCE_SCORE:
    detected_type = best_match
else:
    # Ask user to confirm or select
```

### 3. Machine Learning Detection
Replace keyword matching with ML classification:
```python
from sklearn.naive_bayes import MultinomialNB
# Train on historical tickets
```

### 4. Multi-Type Tickets
Support tickets that span multiple types:
```python
detected_types: List[TicketType]  # Multiple types
# Merge rules from all detected types
```

## Migration from Old System

If you have existing tickets validated with the old system (no ticket types):

```sql
-- All old validation_history records have NULL ticket_type_id
-- This is fine - they remain queryable

-- To retroactively detect types (optional):
UPDATE validation_history vh
SET ticket_type_id = (
    SELECT id FROM ticket_types
    WHERE LOWER(vh.ticket_text) LIKE CONCAT('%', JSON_UNQUOTE(JSON_EXTRACT(detection_keywords, '$[0]')), '%')
    LIMIT 1
)
WHERE ticket_type_id IS NULL;
```

## Troubleshooting

### Bot detects wrong ticket type
**Solution:** Refine detection keywords or add more specific keywords

```sql
UPDATE ticket_types 
SET detection_keywords = '["точное", "специфичное", "ключевое слово"]'
WHERE id = 1;
```

### Too many/few rules applied
**Solution:** Check rule mappings

```sql
-- See which rules are mapped to a type
SELECT vr.rule_name 
FROM validation_rules vr
JOIN ticket_type_rules ttr ON vr.id = ttr.validation_rule_id
WHERE ttr.ticket_type_id = 1;
```

### No ticket type detected
**Solution:** Add more detection keywords or lower specificity

```sql
-- Add general fallback keywords
UPDATE ticket_types 
SET detection_keywords = JSON_ARRAY_APPEND(detection_keywords, '$', 'заявка')
WHERE id = 1;
```

---

**Version:** 2.0.0  
**Last Updated:** 21 января 2026  
**Feature:** Ticket Type Detection and Smart Validation
