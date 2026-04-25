import re
from datetime import datetime

def validate_gas_input(text):
    # Mimicking handlers.py logic
    m = re.match(r"^\s*(\d+)\s+(\d{1,2}/\d{1,2}/\d{4})\s*$", text)
    if not m:
        return "FAIL: Regex mismatch"
        
    try:
        amount_kg = float(m.group(1))
        d_str = m.group(2)
        
        if amount_kg <= 0:
            return "FAIL: Amount <= 0"
            
        p_date = datetime.strptime(d_str, "%d/%m/%Y").date()
        return f"PASS: {amount_kg}kg, {p_date.isoformat()}"
    except Exception as e:
        return f"FAIL: {str(e)}"

test_cases = [
    ("6 22/04/2026", "PASS"),
    ("13 22/04/2026", "PASS"),
    ("0 22/04/2026", "FAIL"),
    ("13 22-04-2026", "FAIL"),
    ("text", "FAIL")
]

for inp, expected in test_cases:
    res = validate_gas_input(inp)
    status = "OK" if expected in res else "WRONG"
    print(f"Input: {inp:15} | Expected: {expected:5} | Result: {res:25} | {status}")
