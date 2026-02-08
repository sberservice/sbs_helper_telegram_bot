-- Update enum to reflect current supported rule types
-- Run this on existing databases BEFORE removing deprecated rules if needed.

START TRANSACTION;

ALTER TABLE ticket_validator_validation_rules
  MODIFY rule_type ENUM(
    'regex',
    'regex_not_match',
    'regex_fullmatch',
    'regex_not_fullmatch',
    'fias_check',
    'custom'
  ) NOT NULL;

COMMIT;
