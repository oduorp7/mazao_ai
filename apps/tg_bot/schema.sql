-- ============================================================
-- Mazao AI — Supabase Schema
-- Run this once in your Supabase SQL editor
-- ============================================================

-- ── Tenants ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tenants (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id         BIGINT UNIQUE NOT NULL,
    telegram_username   TEXT,
    full_name           TEXT,
    business_name       TEXT,
    mpesa_till          TEXT,
    kra_pin             TEXT,
    plan                TEXT DEFAULT 'trial',   -- trial | hustler | biashara
    status              TEXT DEFAULT 'pending', -- pending | trial | active | paused | lapsed
    trial_days_left     INT DEFAULT 14,
    reports_paused      BOOLEAN DEFAULT false,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookup by telegram_id (most common query)
CREATE INDEX IF NOT EXISTS idx_tenants_telegram_id ON tenants(telegram_id);
CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);

-- ── Reports ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    period      TEXT NOT NULL,          -- e.g. "2026-04"
    summary     JSONB DEFAULT '{}',     -- income, expenses, profit, flagged
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reports_tenant_period
    ON reports(tenant_id, created_at DESC);

-- ── Conversations ─────────────────────────────────────────────────────────
-- Tracks multi-step onboarding state per user

CREATE TABLE IF NOT EXISTS conversations (
    telegram_id BIGINT PRIMARY KEY,
    state       TEXT DEFAULT 'idle',
    data        JSONB DEFAULT '{}',
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Row Level Security ────────────────────────────────────────────────────
-- Protects tenant data even if there's a bug in the API.
-- The service key bypasses RLS for your backend.
-- An anon key would only see rows matching the policy.

ALTER TABLE tenants      ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports      ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

-- Service role (your backend) can do everything
CREATE POLICY "service_all_tenants" ON tenants
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_all_reports" ON reports
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_all_conversations" ON conversations
    FOR ALL USING (auth.role() = 'service_role');

-- ── Useful views ──────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW active_tenants AS
    SELECT * FROM tenants
    WHERE status IN ('active', 'trial')
    ORDER BY created_at DESC;

CREATE OR REPLACE VIEW revenue_summary AS
    SELECT
        plan,
        status,
        COUNT(*) as tenant_count
    FROM tenants
    GROUP BY plan, status
-- ── Migration: Sprint 2 (Stabilized P1) ──────────────────────────────────────
-- Adds support for Individuals and SHA/Social Health Insurance
-- [MODIFIED P1] Removed KRA PIN and SHA requirements for faster onboarding.

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS user_type TEXT DEFAULT 'business'; 
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS employment_status TEXT; -- employed | self_employed | unemployed

-- Drop obsolete sensitive columns (P1-T2)
ALTER TABLE tenants DROP COLUMN IF EXISTS kra_pin;
ALTER TABLE tenants DROP COLUMN IF EXISTS sha_number;

-- Missing index for report performance (P1-T5)
CREATE INDEX IF NOT EXISTS idx_reports_period ON reports(period);

-- Language preference for reports (P2-T3)
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS preferred_language TEXT DEFAULT 'en';
