-- P19: Proactive Token Depletion Alert System
-- Migration to add sent-alert flags to token_entries

ALTER TABLE public.token_entries 
ADD COLUMN IF NOT EXISTS alert_7d_sent BOOLEAN DEFAULT FALSE;

ALTER TABLE public.token_entries 
ADD COLUMN IF NOT EXISTS alert_3d_sent BOOLEAN DEFAULT FALSE;

ALTER TABLE public.token_entries 
ADD COLUMN IF NOT EXISTS alert_1d_sent BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN public.token_entries.alert_7d_sent IS 'Flag to prevent duplicate 7-day token depletion alerts in one cycle.';
COMMENT ON COLUMN public.token_entries.alert_3d_sent IS 'Flag to prevent duplicate 3-day token depletion alerts in one cycle.';
COMMENT ON COLUMN public.token_entries.alert_1d_sent IS 'Flag to prevent duplicate 1-day token depletion alerts in one cycle.';
