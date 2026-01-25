-- Migration: Add keyword_weights column to ticket_types table
-- This allows different keywords to have different weights when detecting ticket types

-- Add the keyword_weights column
ALTER TABLE ticket_types 
ADD COLUMN keyword_weights TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci 
COMMENT 'JSON object mapping keywords to their weights (default weight is 1.0)';

-- Example: Set keyword weights for a ticket type
-- Keywords with higher weights will have more influence on detection
-- UPDATE ticket_types 
-- SET keyword_weights = '{"установка": 2.0, "монтаж": 1.5, "-ремонт": 1.0}'
-- WHERE type_name = 'Установка оборудования';
