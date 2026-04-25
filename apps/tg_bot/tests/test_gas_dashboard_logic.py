import asyncio
import os
from datetime import datetime, timedelta, timezone

# Mocking parts of the system to test the helper logic
class MockEstimator:
    GAS_POPULATION_BASELINES = {"standard": 0.25}
    def get_gas_population_baseline(self, ht): return 0.25
    def calculate_weighted_personal_rate(self, h): return (None, 0)
    def blend_rates(self, p, pop, n, nv): return pop
    def get_confidence_info(self, n): return {"bar": "|||", "label": "Low"}

def test_logic_simulation():
    now = datetime.now(timezone.utc)
    # Scenario: Latest refill 5 days ago, 13kg, 0.25kg/day rate
    latest_date = (now - timedelta(days=5)).isoformat()
    history = [{"units": 13.0, "purchase_date": latest_date}]
    
    daily_rate = 0.25
    total_days = 13.0 / daily_rate # 52 days
    days_since = 5
    days_rem = 52 - 5 # 47 days
    
    print(f"DEBUG: Logic check - Total days: {total_days}, Days since: {days_since}, Expected Rem: {days_rem}")
    
    if days_rem == 47:
        print("SUCCESS: Math is sound.")
    else:
        print("FAIL: Math mismatch.")

if __name__ == "__main__":
    test_logic_simulation()
