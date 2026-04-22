-- ============================================================================
-- P17-GAS-INIT: Schema Migration
-- Run this in Supabase SQL Editor
-- ============================================================================

CREATE TABLE IF NOT EXISTS gas_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    amount_kg       NUMERIC NOT NULL,
    purchase_date   DATE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_gas_entries_tenant_id ON gas_entries(tenant_id);

-- Enable RLS
ALTER TABLE gas_entries ENABLE ROW LEVEL SECURITY;

-- Service Role Policy
CREATE POLICY "service_all_gas_entries" ON gas_entries
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================================
-- DONE.
-- ============================================================================
