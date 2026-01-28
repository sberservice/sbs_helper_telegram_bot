-- Migration script to add date_updated column to existing ktr_codes table
-- Run this if you already have the ktr_codes table created

ALTER TABLE `ktr_codes` 
ADD COLUMN `date_updated` varchar(10) DEFAULT NULL COMMENT 'Date when minutes value was updated (dd.mm.yyyy format)' 
AFTER `minutes`;
