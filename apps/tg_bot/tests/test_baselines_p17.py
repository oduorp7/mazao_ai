from apps.agent import estimator

def test_baselines():
    # 1. Gas Path - Basic
    g_basic = estimator.get_gas_population_baseline("basic")
    print(f"Gas (Basic): {g_basic} kg/day | Expected: 0.1")
    
    # 2. Gas Path - Unknown
    g_unknown = estimator.get_gas_population_baseline(None)
    print(f"Gas (Unknown): {g_unknown} kg/day | Expected: 0.25")
    
    # 3. Electricity Path (Regression)
    e_comfort = estimator.get_population_baseline("comfort")
    print(f"Elec (Comfort): {e_comfort} kWh/day | Expected: 4.5")

if __name__ == "__main__":
    test_baselines()
