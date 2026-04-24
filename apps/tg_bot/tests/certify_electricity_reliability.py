import json
import os
import sys
from datetime import datetime, timezone, timedelta

# Add parent directory to path to import estimator
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from apps.agent import estimator

FIXTURE_PATH = "apps/tg_bot/tests/fixtures/electricity_scenarios.json"

def resolve_date(token: str):
    """Resolves relative date tokens like T-0, T-7 to ISO strings."""
    if not isinstance(token, str) or not token.startswith("T-"):
        return token
    try:
        days = int(token.split("-")[1])
        # We use UTC for stability
        dt = datetime.now(timezone.utc) - timedelta(days=days)
        return dt.isoformat().replace("+00:00", "Z")
    except:
        return token

def run_certification():
    print("🚀 Starting Mazao Electricity & Cross-Utility Certification...")
    
    if not os.path.exists(FIXTURE_PATH):
        print(f"❌ Error: Fixture file not found at {FIXTURE_PATH}")
        sys.exit(1)
        
    with open(FIXTURE_PATH, 'r') as f:
        data = json.load(f)
        
    scenarios = data.get("scenarios", [])
    total = len(scenarios)
    passed = 0
    family_stats = {}

    for s in scenarios:
        sid = s["scenario_id"]
        family = s["family"]
        h_type = s["household_type"]
        events = s["events"]
        expected = s["expected"]
        
        print(f"\n[Scenario: {sid}] ({family})")
        
        if family not in family_stats:
            family_stats[family] = {"total": 0, "passed": 0}
        family_stats[family]["total"] += 1

        try:
            # Prepare history format for estimator
            history = [
                {"units": float(e["units"]), "purchase_date": resolve_date(e["purchase_date"])} 
                for e in events
            ]
            history.sort(key=lambda x: x["purchase_date"], reverse=True)
            
            # 1. Utility-Specific Logic (Electricity vs Gas)
            # Electricity logic is currently in scheduler.py, we mirror it here for certification
            pop_rate = estimator.get_population_baseline(h_type)
            pers_rate, n_valid = estimator.calculate_weighted_personal_rate(history)
            daily_rate = estimator.blend_rates(pers_rate, pop_rate, len(history), n_valid)
            if daily_rate <= 0: daily_rate = pop_rate
            
            conf_info = estimator.get_confidence_info(len(history))
            conf_label = conf_info["label"]
            src_label = estimator.get_source_label(len(history), h_type)
            
            # Calculate days_remaining exactly like scheduler.py
            latest_entry = history[0]
            now = datetime.now(timezone.utc)
            l_date_str = latest_entry["purchase_date"]
            l_date = datetime.fromisoformat(l_date_str.replace("Z", "+00:00"))
            if l_date.tzinfo is None: l_date = l_date.replace(tzinfo=timezone.utc)
            
            days_since = (now - l_date).days
            units_remaining = max(0, float(latest_entry["units"]) - (daily_rate * days_since))
            days_left = estimator.calculate_days_remaining(units_remaining, daily_rate)
            
            # 2. Assertions
            # Days Remaining Range
            days_ok = expected["days_left_min"] <= days_left <= expected["days_left_max"]
            
            # Confidence Label
            conf_ok = conf_label == expected["confidence_label"]
            
            # Source Label
            src_ok = expected["source_label_contains"] in src_label
            
            # Reminder Status (NORMALIZED Electricity logic: 7, 3, 1 days AND not Grid baseline)
            # Future-facing: will fail until normalization implementation
            reminder_expected = expected.get("reminder_expected", False)
            reminder_status = days_left in (7, 3, 1) and conf_label != "Grid baseline"
            
            # P17-T2B: Check for dedup state if provided in fixture
            is_deduped = s.get("alert_7d_sent", False) or s.get("alert_3d_sent", False)
            if is_deduped and days_left in (7, 3):
                reminder_status = False # Should be suppressed if already sent
                
            rem_ok = reminder_status == reminder_expected
            
            scenario_passed = days_ok and conf_ok and src_ok and rem_ok
            
            if scenario_passed:
                print(f"  ✅ PASSED")
                passed += 1
                family_stats[family]["passed"] += 1
            else:
                print(f"  ❌ FAILED")
                if not days_ok: print(f"    - Days Left: {days_left} (Expected {expected['days_left_min']}-{expected['days_left_max']})")
                if not conf_ok: print(f"    - Confidence: '{conf_label}' (Expected '{expected['confidence_label']}')")
                if not src_ok: print(f"    - Source: '{src_label}' (Expected to contain '{expected['source_label_contains']}')")
                if not rem_ok: print(f"    - Reminder: {reminder_status} (Expected {reminder_expected})")

        except Exception as e:
            print(f"  💥 ERROR: {str(e)}")

    print("\n" + "="*40)
    print("FAMILY SUMMARY")
    print("-" * 40)
    for f, stats in family_stats.items():
        status = "✅" if stats["passed"] == stats["total"] else "❌"
        print(f"{status} {f}: {stats['passed']}/{stats['total']} Passed")
    
    print("\n" + "="*40)
    print(f"CERTIFICATION SUMMARY: {passed}/{total} Passed")
    print("="*40)
    
    if passed == total:
        print("🎉 Electricity reliability certified.")
        sys.exit(0)
    else:
        print("⚠️ Certification failed.")
        sys.exit(1)

if __name__ == "__main__":
    run_certification()
