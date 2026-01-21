-- Map validation rules to ticket types
-- This creates the relationships between ticket types and their validation rules
-- Run this after loading initial_validation_rules.sql and initial_ticket_types.sql

-- Note: Assumes the following IDs exist:
-- Ticket Types: 1=Установка, 2=ТО, 3=Ремонт, 4=Регистрация ФНС, 5=Замена
-- Validation Rules: 1=tax_system, 2=activation_code, 3=inn_number, 4=installation_address, 
--                    5=contact_phone, 6=organization_name, 7=contact_person, 8=equipment_type, 
--                    9=service_date, 10=minimum_length

-- Common rules for ALL ticket types
-- These rules apply to every type of ticket

-- Tax system (required for all)
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id, created_timestamp)
VALUES 
(1, 1, UNIX_TIMESTAMP()), -- Installation
(2, 1, UNIX_TIMESTAMP()), -- Maintenance
(3, 1, UNIX_TIMESTAMP()), -- Repair
(4, 1, UNIX_TIMESTAMP()), -- Registration
(5, 1, UNIX_TIMESTAMP()); -- Replacement

-- INN (required for all)
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id, created_timestamp)
VALUES 
(1, 3, UNIX_TIMESTAMP()),
(2, 3, UNIX_TIMESTAMP()),
(3, 3, UNIX_TIMESTAMP()),
(4, 3, UNIX_TIMESTAMP()),
(5, 3, UNIX_TIMESTAMP());

-- Organization name (required for all)
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id, created_timestamp)
VALUES 
(1, 6, UNIX_TIMESTAMP()),
(2, 6, UNIX_TIMESTAMP()),
(3, 6, UNIX_TIMESTAMP()),
(4, 6, UNIX_TIMESTAMP()),
(5, 6, UNIX_TIMESTAMP());

-- Contact person (required for all)
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id, created_timestamp)
VALUES 
(1, 7, UNIX_TIMESTAMP()),
(2, 7, UNIX_TIMESTAMP()),
(3, 7, UNIX_TIMESTAMP()),
(4, 7, UNIX_TIMESTAMP()),
(5, 7, UNIX_TIMESTAMP());

-- Contact phone (required for all)
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id, created_timestamp)
VALUES 
(1, 5, UNIX_TIMESTAMP()),
(2, 5, UNIX_TIMESTAMP()),
(3, 5, UNIX_TIMESTAMP()),
(4, 5, UNIX_TIMESTAMP()),
(5, 5, UNIX_TIMESTAMP());

-- Minimum length (required for all)
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id, created_timestamp)
VALUES 
(1, 10, UNIX_TIMESTAMP()),
(2, 10, UNIX_TIMESTAMP()),
(3, 10, UNIX_TIMESTAMP()),
(4, 10, UNIX_TIMESTAMP()),
(5, 10, UNIX_TIMESTAMP());

-- Type-specific rules

-- Installation: activation code, address, equipment, date
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id, created_timestamp)
VALUES 
(1, 2, UNIX_TIMESTAMP()), -- activation_code
(1, 4, UNIX_TIMESTAMP()), -- installation_address
(1, 8, UNIX_TIMESTAMP()), -- equipment_type
(1, 9, UNIX_TIMESTAMP()); -- service_date

-- Maintenance: equipment, date (no activation code needed)
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id, created_timestamp)
VALUES 
(2, 8, UNIX_TIMESTAMP()), -- equipment_type
(2, 9, UNIX_TIMESTAMP()); -- service_date

-- Repair: equipment (no activation code, may not have planned date)
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id, created_timestamp)
VALUES 
(3, 8, UNIX_TIMESTAMP()); -- equipment_type

-- Registration: activation code, address, equipment
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id, created_timestamp)
VALUES 
(4, 2, UNIX_TIMESTAMP()), -- activation_code
(4, 4, UNIX_TIMESTAMP()), -- installation_address
(4, 8, UNIX_TIMESTAMP()); -- equipment_type

-- Replacement: activation code (new equipment), address, equipment, date
INSERT INTO ticket_type_rules (ticket_type_id, validation_rule_id, created_timestamp)
VALUES 
(5, 2, UNIX_TIMESTAMP()), -- activation_code
(5, 4, UNIX_TIMESTAMP()), -- installation_address
(5, 8, UNIX_TIMESTAMP()), -- equipment_type
(5, 9, UNIX_TIMESTAMP()); -- service_date
