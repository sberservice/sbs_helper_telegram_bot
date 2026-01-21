-- Initial ticket types for different types of service requests
-- Run this after creating the ticket_types and ticket_type_rules tables

-- Ticket Type: Installation (Установка)
INSERT INTO ticket_types 
(type_name, description, detection_keywords, active, created_timestamp)
VALUES 
('Установка оборудования', 
 'Заявка на установку нового кассового оборудования',
 '["установка", "монтаж", "новое оборудование", "подключение", "настройка"]',
 1,
 UNIX_TIMESTAMP());

-- Ticket Type: Maintenance (Техническое обслуживание)
INSERT INTO ticket_types 
(type_name, description, detection_keywords, active, created_timestamp)
VALUES 
('Техническое обслуживание', 
 'Заявка на плановое техническое обслуживание',
 '["техническое обслуживание", "плановое обслуживание", "профилактика", "тех обслуживание", "ТО"]',
 1,
 UNIX_TIMESTAMP());

-- Ticket Type: Repair (Ремонт)
INSERT INTO ticket_types 
(type_name, description, detection_keywords, active, created_timestamp)
VALUES 
('Ремонт', 
 'Заявка на ремонт неисправного оборудования',
 '["ремонт", "не работает", "сломалось", "неисправность", "поломка", "проблема"]',
 1,
 UNIX_TIMESTAMP());

-- Ticket Type: Registration (Регистрация в ФНС)
INSERT INTO ticket_types 
(type_name, description, detection_keywords, active, created_timestamp)
VALUES 
('Регистрация в ФНС', 
 'Заявка на регистрацию ККТ в налоговой',
 '["регистрация", "ФНС", "налоговая", "регистрация ККТ", "постановка на учет"]',
 1,
 UNIX_TIMESTAMP());

-- Ticket Type: Replacement (Замена оборудования)
INSERT INTO ticket_types 
(type_name, description, detection_keywords, active, created_timestamp)
VALUES 
('Замена оборудования', 
 'Заявка на замену существующего оборудования',
 '["замена", "замена кассы", "заменить", "устаревшее оборудование"]',
 1,
 UNIX_TIMESTAMP());
