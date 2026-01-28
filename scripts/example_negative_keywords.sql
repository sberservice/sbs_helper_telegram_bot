-- Example: Adding negative keywords to ticket types
-- This script demonstrates how to use negative keywords to improve ticket type detection

-- Update Installation type to exclude repair/replacement related terms
UPDATE ticket_validator_ticket_types 
SET detection_keywords = '["установка", "монтаж", "новое оборудование", "подключение", "настройка", "-ремонт", "-замена", "-перенос"]'
WHERE type_name = 'Установка оборудования';

-- Update Repair type to exclude new installations
UPDATE ticket_validator_ticket_types 
SET detection_keywords = '["ремонт", "не работает", "сломалось", "неисправность", "поломка", "проблема", "-установка", "-новое"]'
WHERE type_name = 'Ремонт';

-- Update Maintenance type to exclude actual repairs
UPDATE ticket_validator_ticket_types 
SET detection_keywords = '["техническое обслуживание", "плановое обслуживание", "профилактика", "тех обслуживание", "ТО", "-поломка", "-сломалось", "-ремонт"]'
WHERE type_name = 'Техническое обслуживание';

-- Update Replacement type to exclude new installations
UPDATE ticket_validator_ticket_types 
SET detection_keywords = '["замена", "замена кассы", "заменить", "устаревшее оборудование", "-установка", "-новое оборудование"]'
WHERE type_name = 'Замена оборудования';

-- Example: Create a new ticket type for Remote Support with negative keywords
INSERT INTO ticket_validator_ticket_types 
(type_name, description, detection_keywords, active, created_timestamp)
VALUES 
('Удаленная поддержка', 
 'Заявка на удаленную техническую поддержку',
 '["удаленно", "дистанционно", "онлайн", "по телефону", "консультация", "-выезд", "-на месте", "-приехать"]',
 1,
 UNIX_TIMESTAMP());

-- Example: Add negative keywords for field service to exclude remote work
INSERT INTO ticket_validator_ticket_types 
(type_name, description, detection_keywords, active, created_timestamp)
VALUES 
('Выезд специалиста', 
 'Заявка на выезд специалиста на объект',
 '["выезд", "на месте", "приехать", "выехать", "диагностика на объекте", "-удаленно", "-дистанционно", "-по телефону"]',
 1,
 UNIX_TIMESTAMP());
