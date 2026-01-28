-- Initial validation rules for ticket validation module
-- This file contains sample validation rules for common ticket fields
-- Run this after creating the tables from schema.sql

-- Tax System Validation (Система налогообложения)
INSERT INTO ticket_validator_validation_rules 
(rule_name, pattern, rule_type, error_message, active, priority, created_timestamp)
VALUES 
('tax_system', 
 '(?i)(система\\s+налогообложения|налогообложение)\\s*[:\\-]?\\s*(УСН|ОСНО|ПСН|ЕНВД|упрощен|общая)', 
 'regex', 
 'Не указана система налогообложения. Должна быть указана одна из: УСН, ОСНО, ПСН, ЕНВД',
 1,
 10,
 UNIX_TIMESTAMP());

-- Activation Code Validation (Код активации)
INSERT INTO ticket_validator_validation_rules 
(rule_name, pattern, rule_type, error_message, active, priority, created_timestamp)
VALUES 
('activation_code', 
 '(?i)(код\\s+активации|активационный\\s+код)\\s*[:\\-]?\\s*[A-Z0-9]{6,12}', 
 'regex', 
 'Не указан код активации. Должен содержать от 6 до 12 символов (буквы и цифры)',
 1,
 9,
 UNIX_TIMESTAMP());

-- INN Validation (ИНН организации - 10 или 12 цифр)
INSERT INTO ticket_validator_validation_rules 
(rule_name, pattern, rule_type, error_message, active, priority, created_timestamp)
VALUES 
('inn_number', 
 '(?i)(ИНН|инн)\\s*[:\\-]?\\s*\\d{10,12}', 
 'regex', 
 'Не указан ИНН организации или указан в неверном формате. ИНН должен содержать 10 или 12 цифр',
 1,
 8,
 UNIX_TIMESTAMP());

-- Installation Address Validation (Адрес установки)
INSERT INTO ticket_validator_validation_rules 
(rule_name, pattern, rule_type, error_message, active, priority, created_timestamp)
VALUES 
('installation_address', 
 '(?i)(адрес\\s+установки|место\\s+установки|адрес\\s+монтажа)\\s*[:\\-]?\\s*.{10,}', 
 'regex', 
 'Не указан адрес установки или адрес слишком короткий (минимум 10 символов)',
 1,
 7,
 UNIX_TIMESTAMP());

-- Contact Phone Validation (Контактный телефон)
INSERT INTO ticket_validator_validation_rules 
(rule_name, pattern, rule_type, error_message, active, priority, created_timestamp)
VALUES 
('contact_phone', 
 '(?i)(телефон|контактный\\s+телефон|тел)\\s*[:\\-]?\\s*\\+?[78]?[\\s\\-]?\\(?\\d{3}\\)?[\\s\\-]?\\d{3}[\\s\\-]?\\d{2}[\\s\\-]?\\d{2}', 
 'regex', 
 'Не указан контактный телефон или указан в неверном формате',
 1,
 6,
 UNIX_TIMESTAMP());

-- Organization Name Validation (Название организации)
INSERT INTO ticket_validator_validation_rules 
(rule_name, pattern, rule_type, error_message, active, priority, created_timestamp)
VALUES 
('organization_name', 
 '(?i)(наименование\\s+организации|название\\s+организации|организация|компания)\\s*[:\\-]?\\s*.{3,}', 
 'regex', 
 'Не указано наименование организации',
 1,
 5,
 UNIX_TIMESTAMP());

-- Contact Person Validation (Контактное лицо)
INSERT INTO ticket_validator_validation_rules 
(rule_name, pattern, rule_type, error_message, active, priority, created_timestamp)
VALUES 
('contact_person', 
 '(?i)(контактное\\s+лицо|ФИО|фио\\s+контакт)\\s*[:\\-]?\\s*.{5,}', 
 'regex', 
 'Не указано контактное лицо или ФИО',
 1,
 4,
 UNIX_TIMESTAMP());

-- Equipment Type Validation (Тип оборудования)
INSERT INTO ticket_validator_validation_rules 
(rule_name, pattern, rule_type, error_message, active, priority, created_timestamp)
VALUES 
('equipment_type', 
 '(?i)(тип\\s+оборудования|оборудование|модель)\\s*[:\\-]?\\s*.{3,}', 
 'regex', 
 'Не указан тип оборудования',
 1,
 3,
 UNIX_TIMESTAMP());

-- Service Date Validation (Дата обслуживания)
INSERT INTO ticket_validator_validation_rules 
(rule_name, pattern, rule_type, error_message, active, priority, created_timestamp)
VALUES 
('service_date', 
 '(?i)(дата\\s+обслуживания|дата\\s+установки|дата)\\s*[:\\-]?\\s*\\d{1,2}[./\\-]\\d{1,2}[./\\-]\\d{2,4}', 
 'regex', 
 'Не указана дата обслуживания или дата в неверном формате (ДД.ММ.ГГГГ)',
 1,
 2,
 UNIX_TIMESTAMP());

-- Minimum Length Check (Общая проверка длины заявки)
INSERT INTO ticket_validator_validation_rules 
(rule_name, pattern, rule_type, error_message, active, priority, created_timestamp)
VALUES 
('minimum_length', 
 'min:50', 
 'length', 
 'Заявка слишком короткая. Минимальная длина - 50 символов',
 1,
 1,
 UNIX_TIMESTAMP());
