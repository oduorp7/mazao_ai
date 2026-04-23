-- P17: Durable Gas Alert Deduplication System
-- Migration to add sent-alert flags to gas_entries
-- Mirrors token_entries pattern for cross-utility consistency.

ALTER TABLE public.gas_entries 
ADD COLUMN IF NOT EXISTS alert_7d_sent BOOLEAN DEFAULT FALSE;

ALTER TABLE public.gas_entries 
ADD COLUMN IF NOT EXISTS alert_3d_sent BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN public.gas_entries.alert_7d_sent IS 'Flag to prevent duplicate 7-day gas depletion alerts in one cycle.';
COMMENT ON COLUMN public.gas_entries.alert_3d_sent IS 'Flag to prevent duplicate 3-day gas depletion alerts in one cycle.';
