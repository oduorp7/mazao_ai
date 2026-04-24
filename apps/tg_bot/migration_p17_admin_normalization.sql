-- ============================================================
-- Migration: Admin Plan Normalization (P17-T4I)
-- Normalizes legacy plan names to Free/Core/Pro
-- ============================================================

-- 1. Biashara -> Pro
UPDATE tenants 
SET plan = 'pro' 
WHERE plan = 'biashara';

-- 2. Mtu Wenyewe -> Core
UPDATE tenants 
SET plan = 'core' 
WHERE plan = 'mtu_wenyewe';

-- 3. Hustler -> Free (Legacy legacy)
UPDATE tenants 
SET plan = 'free' 
WHERE plan = 'hustler';

-- 4. Catch-all: Anything unknown becomes Free
UPDATE tenants 
SET plan = 'free' 
WHERE plan NOT IN ('free', 'trial', 'core', 'pro');

-- 5. Status normalization: if plan is free and status was active, set to lapsed
UPDATE tenants
SET status = 'lapsed'
WHERE plan = 'free' AND status = 'active';

-- Verify counts (commented out for execution)
-- SELECT plan, count(*) FROM tenants GROUP BY plan;
