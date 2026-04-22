import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Tuple

POPULATION_BASELINES = {
    "basic": 0.8,
    "standard": 2.5,
    "comfort": 4.5,
    "business": 8.0
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

def get_population_baseline(household_type: str) -> float:
    """Returns daily rate from population baselines."""
    return POPULATION_BASELINES.get(household_type.lower(), POPULATION_BASELINES["standard"])

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
            # Rate = units of r2 consumed between d2 and d1
            rate = float(r2["units"]) / days
            rates.append(rate)

    n_valid_intervals = len(rates)

    if not rates:
        return (None, 0)

    # Exponential decay weights — most recent interval carries 40% weight
    weights = [0.40, 0.25, 0.15, 0.10, 0.07, 0.03]
    actual_weights = weights[:n_valid_intervals]
    # Re-normalize weights if fewer than 6 valid intervals
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
