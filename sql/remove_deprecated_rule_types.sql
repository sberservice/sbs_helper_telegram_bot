-- Remove deprecated rule types: required_field, format, length
-- This script deletes rules of these types and their associations.

START TRANSACTION;

-- Inspect how many rules will be removed
SELECT COUNT(*) AS rules_to_remove
FROM ticket_validator_validation_rules
WHERE rule_type IN ('required_field', 'format', 'length');

-- Remove rule expectations in templates (if any)
DELETE FROM ticket_validator_template_rule_tests
WHERE validation_rule_id IN (
    SELECT id FROM ticket_validator_validation_rules
    WHERE rule_type IN ('required_field', 'format', 'length')
);

-- Remove rule assignments to ticket types (if any)
DELETE FROM ticket_validator_ticket_type_rules
WHERE validation_rule_id IN (
    SELECT id FROM ticket_validator_validation_rules
    WHERE rule_type IN ('required_field', 'format', 'length')
);

-- Finally remove the rules themselves
DELETE FROM ticket_validator_validation_rules
WHERE rule_type IN ('required_field', 'format', 'length');

COMMIT;
