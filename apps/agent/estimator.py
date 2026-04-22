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

def calculate_weighted_personal_rate(readings: List[Dict]) -> Optional[float]:
    """Calculates weighted average from actual purchase history.
    readings: List of dicts with 'units' and 'purchase_date'
    """
    if len(readings) < 2:
        return None

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

    if not rates:
        return None

    # Exponential decay weights
    weights = [0.40, 0.25, 0.15, 0.10, 0.07, 0.03]
    actual_weights = weights[:len(rates)]
    # Re-normalize weights if fewer than 6 readings
    weight_sum = sum(actual_weights)
    normalized_weights = [w / weight_sum for w in actual_weights]

    weighted_rate = sum(r * w for r, w in zip(rates, normalized_weights))
    return round(weighted_rate, 2)

def blend_rates(personal_rate: Optional[float], population_rate: float, n_readings: int) -> float:
    """Smoothly transitions from population to personal rate."""
    if personal_rate is None or n_readings <= 1:
        return population_rate
    
    # n is number of entries. We need at least 2 entries to have 1 interval (personal rate).
    # Transition: at 7+ entries, we are 100% personal.
    # Weight personal based on reading count n
    personal_weight = min(1.0, (n_readings - 1) * 0.15)
    population_weight = max(0.0, 1.0 - personal_weight)
    
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
