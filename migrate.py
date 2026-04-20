import asyncio
from apps.tg_bot.db import get_client

async def run_migrations():
    client = get_client()
    print("Executing migrations...")
    
    # List of SQL commands to run
    sql_commands = [
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMPTZ;",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMPTZ;",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS phone_number TEXT;",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT false;",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS referral_code TEXT;",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS referred_by UUID REFERENCES tenants(id);",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS referral_discount BOOLEAN DEFAULT false;",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS household_size INT DEFAULT 4;",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS till_number TEXT;",
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID REFERENCES tenants(id),
            message         TEXT NOT NULL,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        );
        """,
        "ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;",
        "CREATE POLICY IF NOT EXISTS service_all_feedback ON feedback FOR ALL USING (auth.role() = 'service_role');"
    ]
    
    for sql in sql_commands:
        try:
            print(f"Running: {sql[:50]}...")
            # Using rpc to execute SQL if available, or just printing instructions
            # Since I can't easily run SQL directly via the client without a custom RPC function,
            # I will try to use the client's internal mechanisms or just report back.
            res = client.rpc("exec_sql", {"sql": sql}).execute()
            print(f"Result: {res}")
        except Exception as e:
            print(f"Error running command: {e}")

if __name__ == "__main__":
    asyncio.run(run_migrations())
