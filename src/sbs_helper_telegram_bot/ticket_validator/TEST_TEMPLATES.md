# Test Templates System

## Overview

The test templates system allows administrators to automatically verify that validation rules work correctly. Instead of being user-facing examples, templates are now used as test cases that define expected validation outcomes.

## Key Concepts

### Test Template
A sample ticket text with:
- **Expected Result**: Whether the overall validation should pass or fail
- **Rule Expectations**: Which specific rules this template tests and whether each should pass or fail

### Automatic Testing
When you run a test on a template:
1. The system validates the template text against all configured rules
2. It compares actual results with expected results
3. Reports any mismatches (rules that behaved differently than expected)

## Database Schema

### Modified: `ticket_templates`
Added columns:
- `expected_result` ENUM('pass', 'fail') - Overall expected validation result
- `ticket_type_id` BIGINT - Optional association with a ticket type
- `updated_timestamp` BIGINT - Last update time

### New: `template_rule_tests`
Junction table linking templates to rules:
- `template_id` - Reference to test template
- `validation_rule_id` - Reference to validation rule
- `expected_pass` - Whether this rule should pass (1) or fail (0)
- `notes` - Admin notes about the expectation

### New: `template_test_results`
Stores test run history:
- `template_id` - Which template was tested
- `admin_userid` - Who ran the test
- `overall_pass` - Whether all expectations were met
- `total_rules_tested` - Number of rules tested
- `rules_passed_as_expected` - Rules that matched expectations
- `rules_failed_unexpectedly` - Rules that didn't match expectations
- `details_json` - Detailed per-rule results

## Usage

### Access
- Templates are **admin-only** - regular users cannot see or use them
- Access via Admin Panel → "🧪 Тест шаблоны" button
- Or from Validator submenu → "🧪 Тест шаблонов" (admin only)

### Creating a Test Template

1. Go to Admin Panel → "🧪 Тест шаблоны"
2. Click "➕ Создать шаблон"
3. Enter:
   - **Name**: Descriptive name (e.g., "Тест: Отсутствует ИНН")
   - **Text**: Sample ticket text to test
   - **Description**: What this template tests
   - **Expected Result**: pass or fail

### Configuring Rule Expectations

After creating a template:
1. Click on the template in the list
2. Click "📋 Управление правилами"
3. Click "➕ Добавить правило"
4. Select a rule and specify if it should pass or fail

### Running Tests

**Single Template:**
1. Click on a template
2. Click "▶️ Запустить тест"

**All Templates:**
1. Click "▶️ Запустить все тесты" in the templates menu
2. Or use "🧪 Тест шаблонов" button from validator submenu

### Interpreting Results

✅ **Test Passed**: All rules behaved as expected
❌ **Test Failed**: Some rules didn't match expectations

The system shows:
- Which rules matched expectations
- Which rules had mismatches
- Expected vs actual outcome for each mismatched rule

## Example Workflow

1. **Create template** "Тест: Валидная заявка" with a complete, valid ticket
   - Set expected_result = 'pass'

2. **Add rule expectations**:
   - tax_system → should pass ✅
   - inn_number → should pass ✅
   - activation_code → should pass ✅

3. **Run test** to verify the rules correctly identify the ticket as valid

4. **Create another template** "Тест: Без ИНН" without INN field
   - Set expected_result = 'fail'
   - Add rule expectations:
     - tax_system → should pass ✅
     - inn_number → should fail ❌
     - activation_code → should pass ✅

5. **Run test** to verify inn_number correctly fails on this ticket

## Installation

The test templates tables are included in the main `schema.sql`. Load sample templates:

```bash
mysql -u user -p database < scripts/sample_test_templates.sql
```

## API Functions

### validation_rules.py

- `create_test_template(...)` - Create new test template
- `update_test_template(...)` - Update template
- `delete_test_template(...)` - Delete template with its expectations
- `toggle_test_template_active(...)` - Enable/disable template
- `load_test_template_by_id(...)` - Get template details
- `list_all_test_templates(...)` - Get all templates

- `set_template_rule_expectation(...)` - Set expected pass/fail for a rule
- `remove_template_rule_expectation(...)` - Remove rule from template
- `get_template_rule_expectations(...)` - Get all expectations for template
- `get_rules_not_in_template(...)` - Get rules available to add

- `run_template_validation_test(...)` - Test single template
- `run_all_template_tests(...)` - Test all active templates
- `get_template_test_history(...)` - Get test run history

## Benefits

1. **Regression Testing**: Verify rules still work after changes
2. **Documentation**: Templates document expected rule behavior
3. **Confidence**: Automatic tests ensure validation logic is correct
4. **Audit Trail**: Test results are stored for review
