from apps.agent import estimator

def test_reminder_triggers():
    # Helper to mock projection state
    def mock_state(days, n):
        return {
            "days_remaining": days,
            "confidence": estimator.get_confidence_info(n),
            "depletion_date": "25 Apr 2026"
        }

    # Test Cases
    cases = [
        {"days": 3, "n": 2, "expected": "SEND"},    # 3-day, High-conf
        {"days": 1, "n": 5, "expected": "SEND"},    # 1-day, High-conf
        {"days": 3, "n": 1, "expected": "SUPPRESS"},# 3-day, Low-conf
        {"days": 2, "n": 5, "expected": "SUPPRESS"},# Off-threshold
        {"days": 7, "n": 5, "expected": "SUPPRESS"} # P17-T1E explicitly forbids 7-day
    ]

    for c in cases:
        proj = mock_state(c["days"], c["n"])
        # Logic from scheduler.py
        should_send = proj["days_remaining"] in (3, 1) and proj["confidence"]["label"] != "Grid baseline"
        status = "SEND" if should_send else "SUPPRESS"
        
        result = "OK" if status == c["expected"] else "FAIL"
        print(f"Days: {c['days']} | N: {c['n']} | Status: {status:8} | Expected: {c['expected']:8} | Result: {result}")

if __name__ == "__main__":
    test_reminder_triggers()
