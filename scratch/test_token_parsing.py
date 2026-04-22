import sys
from datetime import datetime
from dateutil import parser

def test_parsing():
    formats = [
        "28.3 22/04/2026",
        "28.3 22/4/2026",
        "28.3 22/04/2026 1000",
        "28.3 22/4/2026 1000"
    ]
    
    for f in formats:
        print(f"\nTesting format: {f}")
        try:
            parts = f.split()
            units = float(parts[0].replace(",", ""))
            d_str = parts[1]
            
            # Implementation fix using dateutil
            p_date = parser.parse(d_str, dayfirst=True).date()
            
            amount = None
            if len(parts) >= 3:
                amount = float(parts[2].replace(",", ""))
                
            print(f"SUCCESS: Units={units}, Date={p_date}, Amount={amount}")
        except Exception as e:
            print(f"FAILED: {e}")

if __name__ == "__main__":
    test_parsing()
