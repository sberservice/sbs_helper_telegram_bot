-- Sample test templates for validation rule testing
-- Run this after applying migration_test_templates.sql
-- These templates are used by admins to verify validation rules work correctly

-- Clean up existing templates (optional - remove this line if you want to keep existing templates)
-- TRUNCATE TABLE ticket_validator_template_rule_tests;
-- DELETE FROM ticket_validator_ticket_templates;

-- ============================================
-- TEST TEMPLATE 1: Valid installation ticket (should PASS all rules)
-- ============================================
INSERT INTO ticket_validator_ticket_templates 
(template_name, template_text, description, expected_result, active, created_timestamp)
VALUES 
('Тест: Валидная заявка на установку',
'Заявка на установку оборудования

Наименование организации: ООО "Сервис Плюс"
ИНН: 7723456789
Система налогообложения: УСН

Контактное лицо: Петров Иван Сергеевич
Контактный телефон: +7 (495) 123-45-67

Адрес установки: г. Москва, ул. Ленина, д. 25, офис 301
Дата обслуживания: 15.02.2026

Тип оборудования: Касса АТОЛ 91Ф
Код активации: ABCD1234EFGH5678

Дополнительная информация:
Время визита согласовать с клиентом за день до установки.
Парковка во дворе здания.',
'Полностью заполненная заявка на установку, должна пройти все проверки',
'pass',
1,
UNIX_TIMESTAMP());

-- ============================================
-- TEST TEMPLATE 2: Invalid - missing INN (should FAIL inn_number rule)
-- ============================================
INSERT INTO ticket_validator_ticket_templates 
(template_name, template_text, description, expected_result, active, created_timestamp)
VALUES 
('Тест: Отсутствует ИНН',
'Заявка на установку оборудования

Наименование организации: ООО "Тест"
Система налогообложения: ОСНО

Контактное лицо: Сидоров Алексей
Контактный телефон: +7 (999) 888-77-66

Адрес установки: г. Санкт-Петербург, Невский пр., д. 100
Дата обслуживания: 20.02.2026

Тип оборудования: ККМ Меркурий
Код активации: TEST123456789012',
'Заявка без ИНН - должна провалить проверку inn_number',
'fail',
1,
UNIX_TIMESTAMP());

-- ============================================
-- TEST TEMPLATE 3: Invalid - missing tax system (should FAIL tax_system rule)
-- ============================================
INSERT INTO ticket_validator_ticket_templates 
(template_name, template_text, description, expected_result, active, created_timestamp)
VALUES 
('Тест: Отсутствует система налогообложения',
'Заявка на установку оборудования

Наименование организации: ИП Козлов А.В.
ИНН: 772345678901

Контактное лицо: Козлов Андрей Викторович
Контактный телефон: +7 (916) 555-44-33

Адрес установки: г. Москва, ул. Арбат, д. 15
Дата обслуживания: 25.02.2026

Тип оборудования: Эвотор 7.3
Код активации: EVOT2024XXXYYY',
'Заявка без системы налогообложения - должна провалить проверку tax_system',
'fail',
1,
UNIX_TIMESTAMP());

-- ============================================
-- TEST TEMPLATE 4: Invalid - missing activation code (should FAIL activation_code rule)
-- ============================================
INSERT INTO ticket_validator_ticket_templates 
(template_name, template_text, description, expected_result, active, created_timestamp)
VALUES 
('Тест: Отсутствует код активации',
'Заявка на установку оборудования

Наименование организации: АО "Развитие"
ИНН: 7712345678
Система налогообложения: УСН

Контактное лицо: Новикова Елена Павловна
Контактный телефон: +7 (495) 111-22-33

Адрес установки: г. Москва, Профсоюзная ул., д. 50
Дата обслуживания: 28.02.2026

Тип оборудования: Штрих-М',
'Заявка без кода активации - должна провалить проверку activation_code',
'fail',
1,
UNIX_TIMESTAMP());

-- ============================================
-- TEST TEMPLATE 5: Invalid - missing phone (should FAIL contact_phone rule)
-- ============================================
INSERT INTO ticket_validator_ticket_templates 
(template_name, template_text, description, expected_result, active, created_timestamp)
VALUES 
('Тест: Отсутствует телефон',
'Заявка на установку оборудования

Наименование организации: ООО "Прогресс"
ИНН: 7756781234
Система налогообложения: ОСНО

Контактное лицо: Федоров Дмитрий

Адрес установки: г. Москва, ул. Тверская, д. 7
Дата обслуживания: 01.03.2026

Тип оборудования: АТОЛ 22
Код активации: ATOL2024TEST1234',
'Заявка без телефона - должна провалить проверку contact_phone',
'fail',
1,
UNIX_TIMESTAMP());

-- ============================================
-- TEST TEMPLATE 6: Invalid - missing address (should FAIL installation_address rule)
-- ============================================
INSERT INTO ticket_validator_ticket_templates 
(template_name, template_text, description, expected_result, active, created_timestamp)
VALUES 
('Тест: Отсутствует адрес установки',
'Заявка на установку оборудования

Наименование организации: ООО "ТехноСервис"
ИНН: 7743219876
Система налогообложения: УСН

Контактное лицо: Морозов Сергей Иванович
Контактный телефон: +7 (903) 777-88-99

Дата обслуживания: 05.03.2026

Тип оборудования: АТОЛ Sigma 7
Код активации: SIGMA2024ABC123',
'Заявка без адреса установки - должна провалить проверку installation_address',
'fail',
1,
UNIX_TIMESTAMP());

-- ============================================
-- TEST TEMPLATE 7: Invalid - too short (should FAIL minimum_length rule)
-- ============================================
INSERT INTO ticket_validator_ticket_templates 
(template_name, template_text, description, expected_result, active, created_timestamp)
VALUES 
('Тест: Слишком короткая заявка',
'Заявка
ООО Тест
ИНН: 1234567890',
'Очень короткая заявка - должна провалить проверку minimum_length',
'fail',
1,
UNIX_TIMESTAMP());

-- ============================================
-- TEST TEMPLATE 8: Valid maintenance ticket (should PASS)
-- ============================================
INSERT INTO ticket_validator_ticket_templates 
(template_name, template_text, description, expected_result, active, created_timestamp)
VALUES 
('Тест: Валидная заявка на ТО',
'Заявка на техническое обслуживание

Наименование организации: ЗАО "Электроника"
ИНН: 7701234567
Система налогообложения: ОСНО

Контактное лицо: Кузнецов Владимир Петрович
Контактный телефон: +7 (499) 333-22-11

Адрес: г. Москва, Проспект Мира, д. 89
Дата обслуживания: 10.03.2026

Тип оборудования: Эвотор СТ2Ф

Описание проблемы:
Плановое техническое обслуживание, замена чековой ленты, проверка печатающего механизма.',
'Полностью заполненная заявка на ТО, должна пройти все проверки',
'pass',
1,
UNIX_TIMESTAMP());

-- ============================================
-- TEST TEMPLATE 9: Edge case - valid INN formats
-- ============================================
INSERT INTO ticket_validator_ticket_templates 
(template_name, template_text, description, expected_result, active, created_timestamp)
VALUES 
('Тест: ИНН юрлица (10 цифр)',
'Заявка на регистрацию

Организация: ООО "Десять цифр"
ИНН: 7712345678
Налогообложение: УСН

Контакт: Иванов И.И.
Телефон: +7 (999) 123-45-67

Адрес: г. Москва, ул. Тестовая, д. 1
Оборудование: Касса АТОЛ
Код активации: TEST1234567890',
'Проверка корректного распознавания 10-значного ИНН юридического лица',
'pass',
1,
UNIX_TIMESTAMP());

-- ============================================
-- TEST TEMPLATE 10: Edge case - 12-digit INN (individual)
-- ============================================
INSERT INTO ticket_validator_ticket_templates 
(template_name, template_text, description, expected_result, active, created_timestamp)
VALUES 
('Тест: ИНН ИП (12 цифр)',
'Заявка на регистрацию

ИП Двенадцать Цифр
ИНН: 771234567890
Система налогообложения: ПСН

Контактное лицо: Двенадцать Ц.И.
Телефон: +7 (999) 987-65-43

Адрес установки: г. Москва, ул. Проверочная, д. 12
Оборудование: Меркурий 115Ф
Код активации: MERC2024XYZ123',
'Проверка корректного распознавания 12-значного ИНН индивидуального предпринимателя',
'pass',
1,
UNIX_TIMESTAMP());

-- Note: After inserting templates, you need to configure rule expectations
-- using the admin panel in the bot. Each template should have rules
-- assigned with expected pass/fail outcomes.
-- 
-- Example: For template "Тест: Отсутствует ИНН":
-- - inn_number rule should have expected_pass = 0 (should fail)
-- - All other rules should have expected_pass = 1 (should pass)
