import json
import os
import sys
from datetime import datetime, timezone

# Add parent directories to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from apps.agent import estimator

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), 'fixtures/gas_scenarios.json')

def run_certification():
    print("🚀 Starting Mazao Gas Reliability Certification...")
    
    if not os.path.exists(FIXTURE_PATH):
        print(f"❌ Error: Fixture file not found at {FIXTURE_PATH}")
        sys.exit(1)
        
    with open(FIXTURE_PATH, 'r') as f:
        data = json.load(f)
        
    scenarios = data.get("scenarios", [])
    total = len(scenarios)
    passed = 0
    results = []

    for s in scenarios:
        sid = s["scenario_id"]
        family = s["family"]
        h_type = s["household_type"]
        events = s["events"]
        expected = s["expected"]
        
        print(f"\n[Scenario: {sid}] ({family})")
        
        # Prepare history format for estimator
        history = [{"units": float(e["amount_kg"]), "purchase_date": e["purchase_date"]} for e in events]
        # Sort history desc (most recent first) as required by estimator
        history.sort(key=lambda x: x["purchase_date"], reverse=True)
        
        try:
            # Execute projection
            proj = estimator.get_gas_projection_state(history, h_type)
            src_label = estimator.get_gas_source_label(len(history), h_type)
            
            # Assertions
            days_left = proj["days_remaining"]
            conf_label = proj["confidence"]["label"]
            
            # 1. Days Remaining Range
            days_ok = expected["days_left_min"] <= days_left <= expected["days_left_max"]
            # 2. Confidence Label Exact
            conf_ok = conf_label == expected["confidence_label"]
            # 3. Source Label Contains
            src_ok = expected["source_label_contains"].lower() in src_label.lower()
            
            scenario_passed = days_ok and conf_ok and src_ok
            
            if scenario_passed:
                print(f"  ✅ PASSED")
                passed += 1
            else:
                print(f"  ❌ FAILED")
                if not days_ok: print(f"    - Days Left: {days_left} (Expected {expected['days_left_min']}-{expected['days_left_max']})")
                if not conf_ok: print(f"    - Confidence: '{conf_label}' (Expected '{expected['confidence_label']}')")
                if not src_ok: print(f"    - Source: '{src_label}' (Expected to contain '{expected['source_label_contains']}')")
                
            results.append({"id": sid, "passed": scenario_passed})
            
        except Exception as e:
            print(f"  💥 CRASH: {str(e)}")
            results.append({"id": sid, "passed": False, "error": str(e)})

    print("\n" + "="*40)
    print(f"CERTIFICATION SUMMARY: {passed}/{total} Passed")
    print("="*40)
    
    if passed == total:
        print("🎉 Gas reliability certified for V1 families.")
        sys.exit(0)
    else:
        print("⚠️ Certification failed. Check individual scenario outputs.")
        sys.exit(1)

if __name__ == "__main__":
    run_certification()
