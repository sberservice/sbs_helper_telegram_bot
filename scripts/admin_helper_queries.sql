-- Admin Helper SQL Queries
-- Quick reference for common admin database operations

-- =====================================================
-- GRANT ADMIN ACCESS
-- =====================================================

-- Make a user an administrator
UPDATE users SET is_admin = 1 WHERE userid = YOUR_TELEGRAM_USER_ID;

-- Remove admin access
UPDATE users SET is_admin = 0 WHERE userid = YOUR_TELEGRAM_USER_ID;

-- List all admins
SELECT userid, first_name, last_name, username 
FROM users 
WHERE is_admin = 1;


-- =====================================================
-- VIEW VALIDATION RULES
-- =====================================================

-- List all active validation rules
SELECT id, rule_name, rule_type, priority, active
FROM validation_rules
WHERE active = 1
ORDER BY priority DESC, rule_name;

-- View a specific rule with full details
SELECT * FROM validation_rules WHERE id = RULE_ID;

-- Count rules by type
SELECT rule_type, COUNT(*) as count
FROM validation_rules
WHERE active = 1
GROUP BY rule_type;


-- =====================================================
-- VIEW TICKET TYPES AND ASSIGNMENTS
-- =====================================================

-- List all ticket types with rule counts
SELECT 
    tt.id,
    tt.type_name,
    tt.description,
    COUNT(ttr.validation_rule_id) as rule_count
FROM ticket_types tt
LEFT JOIN ticket_type_rules ttr ON tt.id = ttr.ticket_type_id
WHERE tt.active = 1
GROUP BY tt.id, tt.type_name, tt.description
ORDER BY tt.type_name;

-- View all rules assigned to a specific ticket type
SELECT 
    vr.id,
    vr.rule_name,
    vr.rule_type,
    vr.priority,
    vr.error_message
FROM validation_rules vr
INNER JOIN ticket_type_rules ttr ON vr.id = ttr.validation_rule_id
WHERE ttr.ticket_type_id = TICKET_TYPE_ID
    AND vr.active = 1
ORDER BY vr.priority DESC, vr.rule_name;

-- Find rules NOT assigned to a specific ticket type
SELECT 
    vr.id,
    vr.rule_name,
    vr.rule_type,
    vr.priority
FROM validation_rules vr
WHERE vr.active = 1
    AND vr.id NOT IN (
        SELECT validation_rule_id 
        FROM ticket_type_rules 
        WHERE ticket_type_id = TICKET_TYPE_ID
    )
ORDER BY vr.priority DESC, vr.rule_name;


-- =====================================================
-- MANUAL RULE OPERATIONS
-- =====================================================

-- Manually create a validation rule
INSERT INTO validation_rules 
    (rule_name, pattern, rule_type, error_message, priority, active, created_timestamp, updated_timestamp)
VALUES 
    ('Rule Name', 'Pattern or Parameter', 'regex', 'Error message', 10, 1, UNIX_TIMESTAMP(), UNIX_TIMESTAMP());

-- Update rule priority
UPDATE validation_rules 
SET priority = NEW_PRIORITY, updated_timestamp = UNIX_TIMESTAMP()
WHERE id = RULE_ID;

-- Activate/deactivate rule
UPDATE validation_rules 
SET active = 1, updated_timestamp = UNIX_TIMESTAMP()
WHERE id = RULE_ID;

-- Delete rule assignment
DELETE FROM ticket_type_rules 
WHERE ticket_type_id = TYPE_ID AND validation_rule_id = RULE_ID;


-- =====================================================
-- VALIDATION HISTORY QUERIES
-- =====================================================

-- View recent validation failures
SELECT 
    vh.id,
    vh.userid,
    u.username,
    tt.type_name,
    vh.validation_result,
    FROM_UNIXTIME(vh.timestamp) as validation_time
FROM validation_history vh
LEFT JOIN users u ON vh.userid = u.userid
LEFT JOIN ticket_types tt ON vh.ticket_type_id = tt.id
WHERE vh.validation_result = 'invalid'
ORDER BY vh.timestamp DESC
LIMIT 20;

-- Count validations by ticket type
SELECT 
    tt.type_name,
    COUNT(*) as total_validations,
    SUM(CASE WHEN vh.validation_result = 'valid' THEN 1 ELSE 0 END) as passed,
    SUM(CASE WHEN vh.validation_result = 'invalid' THEN 1 ELSE 0 END) as failed
FROM validation_history vh
LEFT JOIN ticket_types tt ON vh.ticket_type_id = tt.id
GROUP BY tt.type_name
ORDER BY total_validations DESC;

-- Find most common validation failures
SELECT 
    failed_rules,
    COUNT(*) as frequency
FROM validation_history
WHERE validation_result = 'invalid'
    AND failed_rules IS NOT NULL
GROUP BY failed_rules
ORDER BY frequency DESC
LIMIT 10;


-- =====================================================
-- TICKET TYPE OPERATIONS
-- =====================================================

-- Create new ticket type
INSERT INTO ticket_types
    (type_name, description, detection_keywords, active, created_timestamp)
VALUES
    ('Type Name', 'Description', '["keyword1", "keyword2", "keyword3"]', 1, UNIX_TIMESTAMP());

-- Update ticket type keywords
UPDATE ticket_types
SET detection_keywords = '["new_keyword1", "new_keyword2"]'
WHERE id = TYPE_ID;

-- View ticket type with keywords parsed
SELECT 
    id,
    type_name,
    description,
    detection_keywords,
    active
FROM ticket_types
WHERE id = TYPE_ID;


-- =====================================================
-- BULK OPERATIONS
-- =====================================================

-- Assign multiple rules to a ticket type at once
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id)
VALUES 
    (TYPE_ID, RULE_ID_1),
    (TYPE_ID, RULE_ID_2),
    (TYPE_ID, RULE_ID_3);

-- Copy all rule assignments from one type to another
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id)
SELECT NEW_TYPE_ID, validation_rule_id
FROM ticket_type_rules
WHERE ticket_type_id = SOURCE_TYPE_ID;

-- Deactivate all rules of a specific type
UPDATE validation_rules
SET active = 0, updated_timestamp = UNIX_TIMESTAMP()
WHERE rule_type = 'RULE_TYPE';


-- =====================================================
-- MAINTENANCE QUERIES
-- =====================================================

-- Find orphaned rules (not assigned to any ticket type)
SELECT 
    vr.id,
    vr.rule_name,
    vr.rule_type
FROM validation_rules vr
WHERE vr.active = 1
    AND NOT EXISTS (
        SELECT 1 
        FROM ticket_type_rules ttr 
        WHERE ttr.validation_rule_id = vr.id
    )
ORDER BY vr.rule_name;

-- Find duplicate rules by name
SELECT rule_name, COUNT(*) as count
FROM validation_rules
GROUP BY rule_name
HAVING count > 1;

-- Database statistics
SELECT 
    (SELECT COUNT(*) FROM validation_rules WHERE active = 1) as active_rules,
    (SELECT COUNT(*) FROM ticket_types WHERE active = 1) as active_types,
    (SELECT COUNT(*) FROM ticket_type_rules) as total_assignments,
    (SELECT COUNT(*) FROM validation_history) as total_validations,
    (SELECT COUNT(*) FROM users WHERE is_admin = 1) as admin_count;


-- =====================================================
-- EXAMPLE USAGE
-- =====================================================

-- Example: Create and assign a new INN validation rule

-- 1. Create the rule
INSERT INTO validation_rules 
    (rule_name, pattern, rule_type, error_message, priority, active, created_timestamp, updated_timestamp)
VALUES 
    ('Проверка ИНН', 'ИНН:\s*\d{10,12}', 'regex', 'ИНН должен содержать 10 или 12 цифр', 15, 1, UNIX_TIMESTAMP(), UNIX_TIMESTAMP());

-- 2. Get the ID of the newly created rule
SET @new_rule_id = LAST_INSERT_ID();

-- 3. Assign to ticket type (assuming ticket type ID = 1)
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id)
VALUES (1, @new_rule_id);

-- 4. Verify assignment
SELECT 
    tt.type_name,
    vr.rule_name,
    vr.rule_type,
    vr.priority
FROM ticket_type_rules ttr
JOIN ticket_types tt ON ttr.ticket_type_id = tt.id
JOIN validation_rules vr ON ttr.validation_rule_id = vr.id
WHERE vr.id = @new_rule_id;
