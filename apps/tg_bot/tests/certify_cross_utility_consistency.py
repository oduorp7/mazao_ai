import sys
import os
from datetime import datetime, timezone

# Add parent directory to path to import estimator
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from apps.agent import estimator

def run_cross_utility_consistency():
    print("🚀 Starting Mazao Cross-Utility Consistency Certification...")
    
    scenarios = [
        ("confidence_band_alignment", "0-1 history entries always return Grid baseline"),
        ("blend_behavior_alignment", "blend_rates(None, rate, 1, 0) == rate"),
        ("fallback_consistency", "Unknown household_type always falls back to standard"),
        ("label_semantics_consistency", "Gas labels and Electricity labels follow same N-based logic")
    ]
    
    total = len(scenarios)
    passed = 0
    
    print("\n--- Running Consistency Assertions ---")
    
    # 1. Confidence Band Alignment
    n_0_1 = estimator.get_confidence_info(1)["label"]
    n_2_4 = estimator.get_confidence_info(3)["label"]
    n_5_9 = estimator.get_confidence_info(7)["label"]
    n_10_plus = estimator.get_confidence_info(12)["label"]
    
    if n_0_1 == "Grid baseline" and n_2_4 == "Building" and n_5_9 == "Good" and n_10_plus == "High":
        print("✅ confidence_band_alignment: OK")
        passed += 1
    else:
        print(f"❌ confidence_band_alignment: FAILED (Labels: {n_0_1}, {n_2_4}, {n_5_9}, {n_10_plus})")
        
    # 2. Blend Behavior Alignment
    pop_rate = 0.25
    blended = estimator.blend_rates(None, pop_rate, 1, 0)
    if blended == pop_rate:
        print("✅ blend_behavior_alignment: OK")
        passed += 1
    else:
        print(f"❌ blend_behavior_alignment: FAILED (Blended: {blended}, Pop: {pop_rate})")
        
    # 3. Fallback Consistency
    elec_pop = estimator.get_population_baseline("alien")
    gas_pop = estimator.get_gas_population_baseline("alien")
    if elec_pop == estimator.POPULATION_BASELINES["standard"] and gas_pop == estimator.GAS_POPULATION_BASELINES["standard"]:
        print("✅ fallback_consistency: OK")
        passed += 1
    else:
        print(f"❌ fallback_consistency: FAILED (Elec: {elec_pop}, Gas: {gas_pop})")
        
    # 4. Label Semantics Consistency
    elec_label = estimator.get_source_label(1, "standard")
    gas_label = estimator.get_gas_source_label(1, "standard")
    if "Kenya grid baseline" in elec_label and "Population baseline" in gas_label:
        print("✅ label_semantics_consistency: OK")
        passed += 1
    else:
        print(f"❌ label_semantics_consistency: FAILED (Elec: {elec_label}, Gas: {gas_label})")
        
    print("\n" + "="*40)
    print(f"CONSISTENCY SUMMARY: {passed}/{total} Passed")
    print("="*40)
    
    if passed == total:
        print("🎉 Cross-utility consistency certified.")
        sys.exit(0)
    else:
        print("⚠️ Consistency check failed.")
        sys.exit(1)

if __name__ == "__main__":
    run_cross_utility_consistency()
