-- P17-T5: Fuliza Input Contract Standardization Migration
-- Adds nullable columns to support the Full SMS format

ALTER TABLE fuliza_entries
    ADD COLUMN IF NOT EXISTS code VARCHAR(50),
    ADD COLUMN IF NOT EXISTS amount_borrowed NUMERIC,
    ADD COLUMN IF NOT EXISTS access_fee NUMERIC,
    ADD COLUMN IF NOT EXISTS total_deducted NUMERIC;
