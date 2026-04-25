import numpy as np
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
import math as _math

POPULATION_BASELINES = {
    "basic": 0.8,
    "standard": 2.5,
    "comfort": 4.5,
    "business": 8.0
}

GAS_POPULATION_BASELINES = {
    "basic": 0.10,    # Minimal cooking
    "standard": 0.25, # Regular household
    "comfort": 0.45,  # Heavy cooking / large family
    "business": 1.20  # Commercial / catering
}

CONFIDENCE_LABELS = {
    "0-1": {"label": "Grid baseline", "bar": "░░░░░"},
    "2-4": {"label": "Building", "bar": "▓▓░░░"},
    "5-9": {"label": "Good", "bar": "▓▓▓▓░"},
    "10+": {"label": "High", "bar": "▓▓▓▓▓"}
}

SOURCE_LABELS = {
    "0-1": "Kenya grid baseline — {h_type} household",
    "2-4": "early personal estimate",
    "5-9": "your usage history",
    "10+": "your personal average"
}

GAS_SOURCE_LABELS = {
    "0-1": "Population baseline ({h_type} household)",
    "2-4": "Building from refill history",
    "5-9": "Based on your usage history",
    "10+": "High-accuracy personal average"
}

def get_population_baseline(household_type: str) -> float:
    """Returns daily electricity rate from population baselines."""
    return POPULATION_BASELINES.get(household_type.lower(), POPULATION_BASELINES["standard"])

def get_gas_population_baseline(household_type: str) -> float:
    """Returns daily gas rate (kg/day) from population baselines.
    
    P17-T1C: Reuses the existing household_type mapping to ground gas predictions.
    Default: standard (0.25 kg/day).
    """
    if not household_type:
        return GAS_POPULATION_BASELINES["standard"]
    return GAS_POPULATION_BASELINES.get(household_type.lower(), GAS_POPULATION_BASELINES["standard"])

def calculate_days_remaining(units: float, daily_rate: float) -> int:
    """
    Authoritative Mazao AI rounding policy for days remaining.
    Uses CEIL to ensure even a fraction of a day is shown as 1 day left.
    """
    if daily_rate <= 0:
        return 0
    return int(_math.ceil(units / daily_rate))

def get_gas_projection_state(history: List[Dict], h_type: str, refill_kg: float = 0) -> Dict:
    """Calculates burn rate and depletion projection for gas.
    
    If refill_kg > 0, it assumes a refill was just performed today.
    Otherwise, it calculates remaining days based on the latest historical entry.
    """
    n = len(history)
    
    # Baseline & Personal Rate
    pop_rate = get_gas_population_baseline(h_type)
    pers_rate, n_valid = calculate_weighted_personal_rate(history)
    daily_rate = blend_rates(pers_rate, pop_rate, n, n_valid)
    if daily_rate <= 0: daily_rate = pop_rate
    
    # Calculate Days Remaining
    now = datetime.now(timezone.utc)
    
    if refill_kg > 0:
        # Scenario A: Just refilled today
        days_rem = calculate_days_remaining(refill_kg, daily_rate)
    elif n > 0:
        # Scenario B: Standing status from history
        # P17-T1F: Stack same-day inventory to handle top-ups/multi-cylinder refills
        latest = history[0]
        l_date = datetime.fromisoformat(latest["purchase_date"].replace("Z", "+00:00"))
        
        # Aggregate all units purchased on the SAME date as the latest entry
        l_date_only = l_date.date()
        stacked_units = 0
        for entry in history:
            e_date = datetime.fromisoformat(entry["purchase_date"].replace("Z", "+00:00")).date()
            if e_date == l_date_only:
                stacked_units += entry["units"]
            else:
                break # History is sorted desc
        
        # Strip timezone for delta if needed or ensure alignment
        if l_date.tzinfo:
            now_aware = datetime.now(l_date.tzinfo)
            days_since = (now_aware - l_date).days
        else:
            days_since = (datetime.now(timezone.utc) - l_date).days
            
        total_days = stacked_units / daily_rate
        days_rem = calculate_days_remaining(stacked_units - (daily_rate * days_since), daily_rate)
    else:
        # Scenario C: No data
        return {"n": 0, "daily_rate": pop_rate, "days_remaining": 0, "depletion_date": "N/A", "confidence": CONFIDENCE_LABELS["0-1"]}

    depletion_date = (datetime.now(timezone.utc) + timedelta(days=max(0, days_rem))).strftime("%d %b %Y")
    
    return {
        "n": n,
        "daily_rate": daily_rate,
        "days_remaining": days_rem,
        "depletion_date": depletion_date,
        "confidence": get_confidence_info(n)
    }

def calculate_weighted_personal_rate(readings: List[Dict]) -> Tuple[Optional[float], int]:
    """Calculates weighted average from actual purchase history.

    Returns Tuple[rate, n_valid_intervals] where:
      - rate is the weighted daily consumption rate (None if insufficient data)
      - n_valid_intervals is the count of intervals where days > 0

    P16-FIX-01: Always returns the interval count so callers can make
    decisions based on real data quality, not raw row count.
    Same-day entries (days=0) are silently excluded — they produce no
    usable interval and must not inflate the personal confidence weight.

    Args:
        readings: List of dicts with 'units' and 'purchase_date'
    """
    if len(readings) < 2:
        return (None, 0)

    # Sort by date descending (most recent first)
    sorted_readings = sorted(
        readings,
        key=lambda x: x["purchase_date"] if isinstance(x["purchase_date"], datetime) else datetime.fromisoformat(x["purchase_date"].replace("Z", "+00:00")),
        reverse=True
    )

    rates = []
    for i in range(len(sorted_readings) - 1):
        r1 = sorted_readings[i]
        r2 = sorted_readings[i+1]

        d1 = r1["purchase_date"] if isinstance(r1["purchase_date"], datetime) else datetime.fromisoformat(r1["purchase_date"].replace("Z", "+00:00"))
        d2 = r2["purchase_date"] if isinstance(r2["purchase_date"], datetime) else datetime.fromisoformat(r2["purchase_date"].replace("Z", "+00:00"))

        days = (d1 - d2).days
        if days > 0:
            rate = float(r2["units"]) / days
            rates.append(rate)

    n_valid_intervals = len(rates)
    if not rates:
        return (None, 0)

    # P16-FIX-FINAL: Anomaly-Aware Weighting
    # If an interval is an anomaly, we reduce its weight so it doesn't skew the projection.
    weights = [0.40, 0.25, 0.15, 0.10, 0.07, 0.03]
    actual_weights = weights[:n_valid_intervals]
    
    # Calculate median to detect outliers
    sorted_rates = sorted(rates)
    median_rate = sorted_rates[len(sorted_rates)//2]
    
    # Apply weight penalties to anomalies
    for i, rate in enumerate(rates):
        # RULE 1: Statistical Outliers (> 3x or < 0.3x median)
        if n_valid_intervals >= 3:
            if rate > median_rate * 3 or rate < median_rate * 0.3:
                actual_weights[i] = actual_weights[i] * 0.1

        # RULE 2: Top-up Paradox (Interval < 24 hours)
        # If buying tokens twice in a day, it's usually a top-up, not 24h consumption.
        r_curr = sorted_readings[i]
        r_prev = sorted_readings[i+1]
        d_curr = r_curr["purchase_date"] if isinstance(r_curr["purchase_date"], datetime) else datetime.fromisoformat(r_curr["purchase_date"].replace("Z", "+00:00"))
        d_prev = r_prev["purchase_date"] if isinstance(r_prev["purchase_date"], datetime) else datetime.fromisoformat(r_prev["purchase_date"].replace("Z", "+00:00"))
        
        seconds = (d_curr - d_prev).total_seconds()
        if seconds < 86400: # < 24 hours
            # CLAMP: Instead of just penalizing weight, we cap the rate at 1.5x median
            # this prevents the 360 units/day spike from ever entering the average.
            rates[i] = min(rates[i], median_rate * 1.5)
            actual_weights[i] = actual_weights[i] * 0.1 # Still penalize weight
                
    # Re-normalize weights
    weight_sum = sum(actual_weights)
    normalized_weights = [w / weight_sum for w in actual_weights]

    weighted_rate = sum(r * w for r, w in zip(rates, normalized_weights))
    return (round(weighted_rate, 2), n_valid_intervals)


def blend_rates(
    personal_rate: Optional[float],
    population_rate: float,
    n_readings: int,
    n_valid_intervals: int = 0,
) -> float:
    """Smoothly transitions from population to personal rate.

    P16-FIX-01-FINAL: personal_weight is driven by n_valid_intervals —
    the count of intervals where days > 0 from calculate_weighted_personal_rate.
    Same-day entries that produce no usable interval carry zero weight.
    n_readings is retained for backward compatibility only; it is NOT
    used in the weight formula.

    Weight ramp: 1 valid interval → 0.15, 7 → 1.0 (full personal trust).
    Default n_valid_intervals=0 → pure population baseline (safe fallback).

    Args:
        personal_rate: Weighted personal rate from calculate_weighted_personal_rate()
        population_rate: Baseline rate for household type
        n_readings: Total entry count (retained for signature compat — not used in weight)
        n_valid_intervals: Count of intervals with days > 0 (drives personal confidence)
    """
    if personal_rate is None or n_valid_intervals == 0:
        return population_rate

    # Gradual ramp: 1 valid interval → 0.15 weight, 7 → 1.0
    personal_weight = min(1.0, n_valid_intervals * 0.15)
    population_weight = 1.0 - personal_weight

    blended = (personal_rate * personal_weight) + (population_rate * population_weight)
    return round(blended, 2)

def confidence_interval(readings: List[Dict], daily_rate: float) -> Optional[Tuple[float, float]]:
    """Returns (lower, upper) confidence interval using standard deviation."""
    if len(readings) < 3:
        return None
        
    # Calculate historical rates to find std dev
    sorted_readings = sorted(
        readings, 
        key=lambda x: x["purchase_date"] if isinstance(x["purchase_date"], datetime) else datetime.fromisoformat(x["purchase_date"].replace("Z", "+00:00")), 
        reverse=True
    )
    
    rates = []
    for i in range(len(sorted_readings) - 1):
        r1 = sorted_readings[i]
        r2 = sorted_readings[i+1]
        d1 = r1["purchase_date"] if isinstance(r1["purchase_date"], datetime) else datetime.fromisoformat(r1["purchase_date"].replace("Z", "+00:00"))
        d2 = r2["purchase_date"] if isinstance(r2["purchase_date"], datetime) else datetime.fromisoformat(r2["purchase_date"].replace("Z", "+00:00"))
        days = (d1 - d2).days
        if days > 0:
            rates.append(float(r2["units"]) / days)
            
    if len(rates) < 2:
        return None
        
    std_dev = np.std(rates)
    # 95% confidence interval approx +/- 2 std devs
    lower = max(0.1, daily_rate - (1.96 * std_dev))
    upper = daily_rate + (1.96 * std_dev)
    return (round(lower, 2), round(upper, 2))

def detect_anomaly(new_rate: float, historical_readings: List[Dict]) -> bool:
    """Detects if a new reading is an outlier."""
    if len(historical_readings) < 3:
        return False
        
    rates = []
    sorted_readings = sorted(
        historical_readings, 
        key=lambda x: x["purchase_date"] if isinstance(x["purchase_date"], datetime) else datetime.fromisoformat(x["purchase_date"].replace("Z", "+00:00")), 
        reverse=True
    )
    
    for i in range(len(sorted_readings) - 1):
        r1 = sorted_readings[i]
        r2 = sorted_readings[i+1]
        d1 = r1["purchase_date"] if isinstance(r1["purchase_date"], datetime) else datetime.fromisoformat(r1["purchase_date"].replace("Z", "+00:00"))
        d2 = r2["purchase_date"] if isinstance(r2["purchase_date"], datetime) else datetime.fromisoformat(r2["purchase_date"].replace("Z", "+00:00"))
        days = (d1 - d2).days
        if days > 0:
            rates.append(float(r2["units"]) / days)
            
    if len(rates) < 3:
        return False
        
    mean = np.mean(rates)
    std_dev = np.std(rates)
    
    if std_dev == 0:
        return False
        
    return abs(new_rate - mean) > 2 * std_dev

def get_confidence_info(n_readings: int) -> Dict:
    """Returns label and bar for confidence levels."""
    if n_readings <= 1: key = "0-1"
    elif n_readings <= 4: key = "2-4"
    elif n_readings <= 9: key = "5-9"
    else: key = "10+"
    return CONFIDENCE_LABELS[key]

def get_source_label(n_readings: int, household_type: str) -> str:
    """Returns the descriptive source of the rate."""
    if n_readings <= 1: key = "0-1"
    elif n_readings <= 4: key = "2-4"
    elif n_readings <= 9: key = "5-9"
    else: key = "10+"
    
    label = SOURCE_LABELS[key]
    if "{h_type}" in label:
        label = label.format(h_type=household_type.capitalize())
    return label

def get_gas_source_label(n_readings: int, household_type: str) -> str:
    """Returns the descriptive source of the gas rate."""
    if n_readings <= 1: key = "0-1"
    elif n_readings <= 4: key = "2-4"
    elif n_readings <= 9: key = "5-9"
    else: key = "10+"
    
    label = GAS_SOURCE_LABELS[key]
    if "{h_type}" in label:
        label = label.format(h_type=household_type.capitalize())
    return label

def get_cost_breakdown(amount_paid: float, tariff: str = "D1", actual_tkn: Optional[float] = None) -> Dict:
    """
    Calculates electricity vs taxes breakdown for Kenya Power tokens.
    
    P17-T1-FIX: Correct D1 split is 52.5% electricity. 
    Fallbacks: D1=52.5%, others (D2/D3)=50%.
    Actual TknAmt from DB always takes precedence if available.
    """
    if actual_tkn and actual_tkn > 0:
        elec = actual_tkn
        taxes = amount_paid - elec
    else:
        # P17-T1-FIX: Derived from real token data (KES 525.26 / 1000)
        # Never use hardcoded 37/63 split.
        ratio = 0.525 if "D1" in tariff.upper() else 0.50
        elec = amount_paid * ratio
        taxes = amount_paid - elec
        
    return {
        "electricity": round(elec, 2),
        "taxes": round(taxes, 2),
        "percentage": round((elec / amount_paid * 100), 1) if amount_paid > 0 else 0
    }
