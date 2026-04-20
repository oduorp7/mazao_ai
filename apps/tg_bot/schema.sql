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
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMPTZ;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS subscription_active BOOLEAN DEFAULT false;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS founding_member BOOLEAN DEFAULT false;

-- ── Migration: Phase 3 (P3-T4) ────────────────────────────────────────────────
-- Store parsed statement summaries

CREATE TABLE IF NOT EXISTS statements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    period          TEXT, -- e.g. "2026-04"
    total_inflows   NUMERIC DEFAULT 0,
    total_outflows  NUMERIC DEFAULT 0,
    net             NUMERIC DEFAULT 0,
    vat_estimate    NUMERIC DEFAULT 0,
    parsed_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_statements_tenant_id ON statements(tenant_id);
CREATE INDEX IF NOT EXISTS idx_statements_parsed_at ON statements(parsed_at DESC);

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS household_size INT DEFAULT 4;

-- ── Migration: Phase 4 (P4-T1, P4-T2) ──────────────────────────────────────────
-- Utility Prediction Tables

CREATE TABLE IF NOT EXISTS token_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    units           NUMERIC NOT NULL,
    purchase_date   DATE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fuliza_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    balance         NUMERIC NOT NULL,
    due_date        DATE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_token_entries_tenant_id ON token_entries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_fuliza_entries_tenant_id ON fuliza_entries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_fuliza_entries_due_date ON fuliza_entries(due_date);

-- ── Row Level Security (Phase 3 & 4) ───────────────────────────────────────

ALTER TABLE statements      ENABLE ROW LEVEL SECURITY;
ALTER TABLE token_entries   ENABLE ROW LEVEL SECURITY;
ALTER TABLE fuliza_entries   ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_all_statements" ON statements
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_all_token_entries" ON token_entries
    FOR ALL USING (auth.role() = 'service_role');


-- ── Subscriptions (P5-T1) ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    name TEXT NOT NULL,
    amount_kes NUMERIC NOT NULL,
    renewal_day INTEGER NOT NULL CHECK (renewal_day BETWEEN 1 AND 28),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

-- Service Role Policy
CREATE POLICY "service_all_subscriptions" ON subscriptions
    FOR ALL USING (auth.role() = 'service_role');


-- ── Migration: Phase 6 (P6-T4) ────────────────────────────────────────────────
-- Real-time transaction feed support

CREATE TABLE IF NOT EXISTS live_transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID REFERENCES tenants(id),
    trans_id        TEXT UNIQUE NOT NULL,
    trans_time      TIMESTAMPTZ,
    amount          NUMERIC NOT NULL,
    msisdn          TEXT,
    first_name      TEXT,
    bill_ref        TEXT,
    provider        TEXT DEFAULT 'intasend',
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Index for lookup (BillRefNumber or MSISDN)
CREATE INDEX IF NOT EXISTS idx_live_tx_bill_ref ON live_transactions(bill_ref);
CREATE INDEX IF NOT EXISTS idx_live_tx_msisdn ON live_transactions(msisdn);
CREATE INDEX IF NOT EXISTS idx_live_tx_tenant_id ON live_transactions(tenant_id);

-- Add till_number to tenants for matching
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS till_number TEXT;
CREATE INDEX IF NOT EXISTS idx_tenants_till_number ON tenants(till_number);

-- RLS
ALTER TABLE live_transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_all_live_transactions" ON live_transactions
    FOR ALL USING (auth.role() = 'service_role');

-- ── Migration: Phase 7 (P7-T1) ────────────────────────────────────────────────
-- Monetisation & Trial Management

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMPTZ;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMPTZ;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS subscription_active BOOLEAN DEFAULT false;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS phone_number TEXT; -- For payment contact

-- Refine plan enum/defaults if not already robust
ALTER TABLE tenants ALTER COLUMN plan SET DEFAULT 'free';

CREATE TABLE IF NOT EXISTS payment_requests (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID REFERENCES tenants(id),
    amount              NUMERIC NOT NULL,
    phone_number        TEXT NOT NULL,
    account_ref         TEXT NOT NULL,
    intasend_invoice_id TEXT, -- Intasend's unique invoice identifier
    status              TEXT DEFAULT 'pending', -- pending | confirmed | failed
    created_at          TIMESTAMPTZ DEFAULT now(),
    confirmed_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pay_req_tenant_id ON payment_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pay_req_intasend_id ON payment_requests(intasend_invoice_id);
CREATE INDEX IF NOT EXISTS idx_pay_req_status ON payment_requests(status);

-- RLS for payment_requests
ALTER TABLE payment_requests ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_payment_requests" ON payment_requests
    FOR ALL USING (auth.role() = 'service_role');
