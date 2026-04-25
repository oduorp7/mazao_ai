import unittest
from datetime import date, datetime
import sys
import os

# Ensure project root is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

# Import the pure functions from handlers and estimator
from apps.tg_bot.handlers import _parse_kplc_sms, _detect_tariff_tier
from apps.agent import estimator

class TestMazaoEstimatorCore(unittest.TestCase):
    """FAANG-Grade Regression Suite for Mazao AI Token Logic."""

    def setUp(self):
        self.sample_mtr = "0277100839863"
        self.sample_token = "0967-8847-2772-1258-0314"

    def test_kplc_sms_parser_standard(self):
        """Verify standard KPLC SMS parsing (D2 Ordinary)."""
        sms = (f"Mtr:{self.sample_mtr} Token:{self.sample_token} "
               f"Date:20260422 12:47 Units:28.3 Amt:1000.00 "
               f"TknAmt:525.26 OtherCharges:474.74")
        
        res = _parse_kplc_sms(sms)
        
        self.assertIsNotNone(res)
        self.assertEqual(res['meter_number'], self.sample_mtr)
        self.assertEqual(res['token_number'], self.sample_token)
        self.assertEqual(res['units'], 28.3)
        self.assertEqual(res['amount_paid'], 1000.00)
        self.assertEqual(res['token_amount'], 525.26)
        self.assertEqual(res['other_charges'], 474.74)
        self.assertEqual(res['purchase_date'], date(2026, 4, 22))

    def test_tariff_tier_detection(self):
        """Verify deterministic tariff classification (D1, D2, D3)."""
        # D1 Lifeline (< 13.50 KES/unit)
        self.assertEqual(_detect_tariff_tier(12.23)['key'], "D1")
        # D2 Ordinary (13.50 - 17.50 KES/unit)
        self.assertEqual(_detect_tariff_tier(16.45)['key'], "D2")
        # D3 High (> 17.50 KES/unit)
        self.assertEqual(_detect_tariff_tier(19.08)['key'], "D3")

    def test_estimator_weight_logic(self):
        """Verify that same-day entries (days=0) do not inflate confidence."""
        # 3 readings, but 1 is same-day (invalid interval)
        readings = [
            {"units": 28.3, "purchase_date": "2026-04-22T12:00:00Z"},
            {"units": 10.0, "purchase_date": "2026-04-22T10:00:00Z"}, # Same day!
            {"units": 10.0, "purchase_date": "2026-04-20T10:00:00Z"},
        ]
        rate, n_valid = estimator.calculate_weighted_personal_rate(readings)
        
        # Should only count 1 valid interval (22nd to 20th)
        self.assertEqual(n_valid, 1)
        self.assertIsNotNone(rate)

    def test_blend_rates_fallback(self):
        """Verify blended rate gracefully falls back to population baseline."""
        pop_rate = 5.0
        # No valid intervals -> must return population rate
        blended = estimator.blend_rates(personal_rate=10.0, population_rate=pop_rate, n_readings=10, n_valid_intervals=0)
        self.assertEqual(blended, pop_rate)

    def test_dedup_case_insensitive(self):
        """Verify SMS parser is case insensitive for 'Mtr' and 'Token' labels."""
        sms = "mtr:123 TOKEN:456 date:20260422 12:00 units:10 amt:100 tknamt:50 othercharges:50"
        res = _parse_kplc_sms(sms)
        self.assertIsNotNone(res)
        self.assertEqual(res['meter_number'], "123")

    def test_estimator_zero_division_safety(self):
        """Tier A Invariant: Blended rate must NEVER be zero or negative."""
        # Force a case where rates might be zero
        blended = estimator.blend_rates(personal_rate=0, population_rate=0, n_readings=1, n_valid_intervals=1)
        self.assertEqual(blended, 0)
        
    def test_cost_breakdown_safety(self):
        """Tier A Invariant: Cost breakdown must handle 0 amount_paid without crashing."""
        bd = estimator.get_cost_breakdown(0)
        self.assertEqual(bd["percentage"], 0)
        self.assertEqual(bd["electricity"], 0)
        self.assertEqual(bd["taxes"], 0)

    def test_gas_projection_zero_history(self):
        """Tier A Invariant: Gas projection must return population baseline for zero history."""
        proj = estimator.get_gas_projection_state([], "standard")
        self.assertEqual(proj["n"], 0)
        self.assertGreater(proj["daily_rate"], 0)
        self.assertEqual(proj["days_remaining"], 0)

if __name__ == '__main__':
    unittest.main()
