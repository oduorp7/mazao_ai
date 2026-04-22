import sys
import os
from datetime import datetime, timedelta, timezone

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from apps.agent import estimator

def simulate_user_history():
    print("SIMULATION START: Debugging the 15.37 Wall")
    
    # Replicating your exact DB state
    readings = [
        {"units": 10.0, "purchase_date": "2026-04-23T10:00:00Z"},
        {"units": 15.0, "purchase_date": "2026-04-23T09:00:00Z"},
        {"units": 15.0, "purchase_date": "2026-04-23T08:00:00Z"},
        {"units": 25.0, "purchase_date": "2026-04-22T22:30:00Z"},
        {"units": 28.3, "purchase_date": "2026-04-22T12:00:00Z"},
        {"units": 30.0, "purchase_date": "2026-04-17T10:00:00Z"},
        {"units": 30.0, "purchase_date": "2026-04-12T10:00:00Z"},
        {"units": 35.0, "purchase_date": "2026-04-07T10:00:00Z"},
        {"units": 35.0, "purchase_date": "2026-04-02T10:00:00Z"},
    ]
    
    pop_rate = 4.5
    n = len(readings)
    
    pers_rate, n_valid = estimator.calculate_weighted_personal_rate(readings)
    daily_rate = estimator.blend_rates(pers_rate, pop_rate, n, n_valid)
    
    print(f"\nFinal Blended Rate: {daily_rate}")
    
    # Let's check why the rounding says 0
    import math
    units = 10.0
    days_floor = int(units / daily_rate)
    days_ceil = int(math.ceil(units / daily_rate))
    
    print(f"Units Left: {units}")
    print(f"Floor Days: {days_floor} (OLD VERSION)")
    print(f"Ceil Days:  {days_ceil} (NEW VERSION)")

if __name__ == "__main__":
    simulate_user_history()
