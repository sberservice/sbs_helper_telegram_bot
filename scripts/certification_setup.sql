-- ============================================================================
-- Certification Module Initial Setup
-- ============================================================================
-- This script creates initial categories and sample questions for the
-- employee certification module.
--
-- Run this after executing schema.sql to populate initial data.
-- ============================================================================

-- ============================================================================
-- Default Settings
-- ============================================================================

INSERT INTO `certification_settings` (`setting_key`, `setting_value`, `description`, `updated_timestamp`)
VALUES 
    ('questions_count', '20', 'Number of questions per test', UNIX_TIMESTAMP()),
    ('time_limit_minutes', '15', 'Time limit for test in minutes', UNIX_TIMESTAMP()),
    ('passing_score_percent', '80', 'Minimum score percentage to pass', UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE 
    `updated_timestamp` = UNIX_TIMESTAMP();

-- ============================================================================
-- Sample Categories
-- ============================================================================

INSERT INTO `certification_categories` (`name`, `description`, `display_order`, `active`, `created_timestamp`)
VALUES
    ('Общие знания', 'Базовые вопросы по работе сервисного инженера', 1, 1, UNIX_TIMESTAMP()),
    ('Оборудование POS', 'Вопросы по POS-терминалам и кассовому оборудованию', 2, 1, UNIX_TIMESTAMP()),
    ('UPOS ошибки', 'Знание кодов ошибок UPOS и способов их устранения', 3, 1, UNIX_TIMESTAMP()),
    ('Техника безопасности', 'Правила техники безопасности при обслуживании оборудования', 4, 1, UNIX_TIMESTAMP()),
    ('Работа с клиентами', 'Стандарты обслуживания и коммуникации с клиентами', 5, 1, UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE 
    `updated_timestamp` = UNIX_TIMESTAMP();

-- ============================================================================
-- Sample Questions
-- ============================================================================

-- Get category IDs (assuming they were just created)
SET @cat_general = (SELECT id FROM certification_categories WHERE name = 'Общие знания' LIMIT 1);
SET @cat_pos = (SELECT id FROM certification_categories WHERE name = 'Оборудование POS' LIMIT 1);
SET @cat_upos = (SELECT id FROM certification_categories WHERE name = 'UPOS ошибки' LIMIT 1);
SET @cat_safety = (SELECT id FROM certification_categories WHERE name = 'Техника безопасности' LIMIT 1);
SET @cat_clients = (SELECT id FROM certification_categories WHERE name = 'Работа с клиентами' LIMIT 1);

-- General knowledge questions
INSERT INTO `certification_questions` 
    (`question_text`, `option_a`, `option_b`, `option_c`, `option_d`, `correct_option`, `explanation`, `difficulty`, `relevance_date`, `active`, `created_timestamp`)
VALUES
    ('Что необходимо сделать в первую очередь при получении заявки на обслуживание?',
     'Сразу выехать на объект',
     'Связаться с клиентом для уточнения деталей',
     'Закрыть заявку как выполненную',
     'Передать заявку другому инженеру',
     'B',
     'Перед выездом необходимо связаться с клиентом для уточнения адреса, времени и характера неисправности',
     'easy', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP()),
     
    ('Какой максимальный срок реагирования на заявку категории "Срочная"?',
     '30 минут',
     '1 час',
     '4 часа',
     '24 часа',
     'C',
     'Согласно SLA, срочные заявки должны быть обработаны в течение 4 часов',
     'medium', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP()),
     
    ('Что такое SLA в контексте сервисного обслуживания?',
     'Тип оборудования',
     'Соглашение об уровне обслуживания',
     'Система логистики',
     'Программное обеспечение',
     'B',
     'SLA (Service Level Agreement) - соглашение об уровне обслуживания между поставщиком услуг и клиентом',
     'easy', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP());

-- POS equipment questions
INSERT INTO `certification_questions` 
    (`question_text`, `option_a`, `option_b`, `option_c`, `option_d`, `correct_option`, `explanation`, `difficulty`, `relevance_date`, `active`, `created_timestamp`)
VALUES
    ('Какое напряжение питания используется для большинства POS-терминалов?',
     '12В постоянного тока',
     '220В переменного тока',
     '5В постоянного тока',
     '48В постоянного тока',
     'A',
     'Большинство POS-терминалов работают от блока питания 12В DC',
     'medium', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP()),
     
    ('Что следует проверить в первую очередь при отсутствии связи терминала с банком?',
     'Заменить терминал',
     'Проверить сетевое подключение и настройки',
     'Перезагрузить сервер банка',
     'Позвонить в службу поддержки банка',
     'B',
     'Сначала необходимо проверить физическое подключение и сетевые настройки терминала',
     'easy', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP()),
     
    ('Какой тип принтера чаще всего используется в POS-терминалах?',
     'Лазерный',
     'Струйный',
     'Термопринтер',
     'Матричный',
     'C',
     'В POS-терминалах используются термопринтеры, не требующие картриджей',
     'easy', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP());

-- UPOS error questions
INSERT INTO `certification_questions` 
    (`question_text`, `option_a`, `option_b`, `option_c`, `option_d`, `correct_option`, `explanation`, `difficulty`, `relevance_date`, `active`, `created_timestamp`)
VALUES
    ('Код ошибки UPOS "E_TIMEOUT" обычно указывает на:',
     'Неправильный PIN-код',
     'Превышение времени ожидания ответа',
     'Недостаточно средств на карте',
     'Карта заблокирована',
     'B',
     'E_TIMEOUT означает, что операция превысила допустимое время ожидания',
     'medium', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP()),
     
    ('При получении ошибки "E_NOHARDWARE" следует:',
     'Перезагрузить систему',
     'Проверить подключение оборудования',
     'Обновить драйверы',
     'Связаться с банком',
     'B',
     'E_NOHARDWARE указывает на отсутствие физического подключения устройства',
     'easy', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP()),
     
    ('Ошибка "E_ILLEGAL" в UPOS означает:',
     'Незаконная операция',
     'Недопустимый параметр или состояние',
     'Проблемы с лицензией',
     'Блокировка устройства',
     'B',
     'E_ILLEGAL указывает на попытку выполнить операцию с недопустимыми параметрами',
     'hard', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP());

-- Safety questions
INSERT INTO `certification_questions` 
    (`question_text`, `option_a`, `option_b`, `option_c`, `option_d`, `correct_option`, `explanation`, `difficulty`, `relevance_date`, `active`, `created_timestamp`)
VALUES
    ('Перед началом работы с электрооборудованием необходимо:',
     'Надеть резиновые перчатки',
     'Отключить питание и убедиться в его отсутствии',
     'Позвать напарника',
     'Открыть все окна в помещении',
     'B',
     'Безопасность требует обязательного отключения питания перед любыми работами',
     'easy', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP()),
     
    ('При обнаружении повреждения изоляции кабеля питания следует:',
     'Заизолировать изолентой и продолжить работу',
     'Немедленно отключить и заменить кабель',
     'Сообщить клиенту и оставить как есть',
     'Проверить работоспособность и решить по ситуации',
     'B',
     'Поврежденная изоляция создает риск поражения током и должна быть устранена заменой кабеля',
     'medium', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP());

-- Client communication questions
INSERT INTO `certification_questions` 
    (`question_text`, `option_a`, `option_b`, `option_c`, `option_d`, `correct_option`, `explanation`, `difficulty`, `relevance_date`, `active`, `created_timestamp`)
VALUES
    ('При опоздании на объект клиента необходимо:',
     'Приехать молча и начать работу',
     'Заранее предупредить клиента о задержке',
     'Перенести визит на другой день',
     'Приехать и извиниться по факту',
     'B',
     'Профессиональный подход требует заблаговременного информирования клиента о любых изменениях',
     'easy', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP()),
     
    ('Если клиент недоволен качеством обслуживания, следует:',
     'Объяснить, что вы всё сделали правильно',
     'Выслушать, извиниться и предложить решение',
     'Направить к руководству',
     'Завершить разговор и уехать',
     'B',
     'Работа с негативом требует активного слушания и конструктивного подхода к решению проблемы',
     'medium', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP()),
     
    ('По завершении работ на объекте необходимо:',
     'Быстро уехать',
     'Получить подпись клиента в акте и объяснить выполненные работы',
     'Отправить отчет по email',
     'Позвонить в офис и доложить',
     'B',
     'Подписание акта и информирование клиента о выполненных работах - обязательная процедура',
     'easy', DATE_ADD(CURDATE(), INTERVAL 6 MONTH), 1, UNIX_TIMESTAMP());

-- ============================================================================
-- Link questions to categories
-- ============================================================================

-- General knowledge questions (IDs 1-3)
INSERT INTO `certification_question_categories` (`question_id`, `category_id`, `created_timestamp`)
SELECT q.id, @cat_general, UNIX_TIMESTAMP()
FROM certification_questions q
WHERE q.question_text LIKE '%заявки%' OR q.question_text LIKE '%SLA%'
ON DUPLICATE KEY UPDATE `created_timestamp` = UNIX_TIMESTAMP();

-- POS equipment questions (IDs 4-6)
INSERT INTO `certification_question_categories` (`question_id`, `category_id`, `created_timestamp`)
SELECT q.id, @cat_pos, UNIX_TIMESTAMP()
FROM certification_questions q
WHERE q.question_text LIKE '%POS%' OR q.question_text LIKE '%терминал%' OR q.question_text LIKE '%принтер%'
ON DUPLICATE KEY UPDATE `created_timestamp` = UNIX_TIMESTAMP();

-- UPOS error questions (IDs 7-9)
INSERT INTO `certification_question_categories` (`question_id`, `category_id`, `created_timestamp`)
SELECT q.id, @cat_upos, UNIX_TIMESTAMP()
FROM certification_questions q
WHERE q.question_text LIKE '%UPOS%' OR q.question_text LIKE '%E_%'
ON DUPLICATE KEY UPDATE `created_timestamp` = UNIX_TIMESTAMP();

-- Safety questions (IDs 10-11)
INSERT INTO `certification_question_categories` (`question_id`, `category_id`, `created_timestamp`)
SELECT q.id, @cat_safety, UNIX_TIMESTAMP()
FROM certification_questions q
WHERE q.question_text LIKE '%электрооборудован%' OR q.question_text LIKE '%изоляци%'
ON DUPLICATE KEY UPDATE `created_timestamp` = UNIX_TIMESTAMP();

-- Client communication questions (IDs 12-14)
INSERT INTO `certification_question_categories` (`question_id`, `category_id`, `created_timestamp`)
SELECT q.id, @cat_clients, UNIX_TIMESTAMP()
FROM certification_questions q
WHERE q.question_text LIKE '%клиент%' OR q.question_text LIKE '%опоздан%' OR q.question_text LIKE '%завершени%'
ON DUPLICATE KEY UPDATE `created_timestamp` = UNIX_TIMESTAMP();

-- ============================================================================
-- Summary
-- ============================================================================
-- After running this script, you will have:
-- - 3 configuration settings (questions_count, time_limit, passing_score)
-- - 5 question categories
-- - 14 sample questions distributed across categories
-- ============================================================================
