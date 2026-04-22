-- ============================================================================
-- P16-ESTIMATOR-FIX-FINAL: Schema Migration (V3 — supersedes V2)
-- Run this in Supabase SQL Editor
-- ============================================================================

-- ── PRE-01: Review dirty test entries BEFORE deleting ────────────────────────
-- Run this SELECT first to see what you have:
-- SELECT id, units, purchase_date, amount_paid, created_at
-- FROM token_entries
-- WHERE tenant_id = (SELECT id FROM tenants WHERE telegram_id = <YOUR_TELEGRAM_ID>)
-- ORDER BY purchase_date ASC;

-- Then delete everything EXCEPT your real 22/04/2026 token:
-- DELETE FROM token_entries
-- WHERE tenant_id = (SELECT id FROM tenants WHERE telegram_id = <YOUR_TELEGRAM_ID>)
--   AND NOT (units = 28.3 AND purchase_date::date = '2026-04-22');

-- Verify: must return 1 after cleanup:
-- SELECT COUNT(*) FROM token_entries
-- WHERE tenant_id = (SELECT id FROM tenants WHERE telegram_id = <YOUR_TELEGRAM_ID>);

-- ── PRE-02: Add new columns (all nullable — backward compatible) ──────────────
ALTER TABLE token_entries ADD COLUMN IF NOT EXISTS meter_number  TEXT;
ALTER TABLE token_entries ADD COLUMN IF NOT EXISTS token_number  TEXT;
ALTER TABLE token_entries ADD COLUMN IF NOT EXISTS token_amount  NUMERIC;
ALTER TABLE token_entries ADD COLUMN IF NOT EXISTS other_charges NUMERIC;
ALTER TABLE token_entries ADD COLUMN IF NOT EXISTS tariff_tier   TEXT;
ALTER TABLE token_entries ADD COLUMN IF NOT EXISTS rate_per_unit NUMERIC;

-- Deduplication: partial UNIQUE index — safe for existing NULL token_number rows
CREATE UNIQUE INDEX IF NOT EXISTS idx_token_entries_token_number
    ON token_entries (token_number)
    WHERE token_number IS NOT NULL;

-- ── Verify columns added ──────────────────────────────────────────────────────
-- SELECT column_name, data_type
-- FROM information_schema.columns
-- WHERE table_name = 'token_entries'
-- ORDER BY ordinal_position;

-- ============================================================================
-- DONE. All columns nullable — no existing data affected.
-- ============================================================================
