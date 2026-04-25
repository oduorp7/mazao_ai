import os
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

# Mock env vars
os.environ["SUPABASE_URL"] = "http://localhost"
os.environ["SUPABASE_SERVICE_KEY"] = "key"

# Import from the actual app
from apps.tg_bot import scheduler as S
from apps.tg_bot import messages as M

async def run_simulation():
    print("STARTING COMPREHENSIVE TOKEN ALERT SIMULATION\n")
    
    bot = AsyncMock()
    
    # Common test setup
    tenant = {"id": "t1", "telegram_id": 12345, "household_type": "standard"}
    
    with patch("apps.tg_bot.scheduler.db.get_all_active_tenants") as mock_active, \
         patch("apps.tg_bot.scheduler.db.get_client") as mock_get_client, \
         patch("apps.tg_bot.scheduler.estimator") as mock_est:
        
        mock_active.return_value = [tenant]
        mock_table = MagicMock()
        mock_get_client.return_value.table.return_value = mock_table
        
        # Mock Estimator: Standard household baseline = 2.5 units/day
        mock_est.get_population_baseline.return_value = 2.5
        mock_est.calculate_weighted_personal_rate.return_value = (None, 0)
        mock_est.blend_rates.return_value = 2.5
        
        # ── SCENARIO 1: 7-Day Threshold (Alert NOT yet sent) ──────────────────
        print("Scenario 1: 7 days remaining, first time...")
        
        purchase_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        entry_data = {
            "id": "entry_7d",
            "units": 20.0, 
            "purchase_date": purchase_date,
            "alert_7d_sent": False,
            "alert_3d_sent": False,
            "alert_1d_sent": False
        }
        
        mock_entry_resp = MagicMock(data=entry_data)
        mock_hist_resp = MagicMock(data=[entry_data])
        
        # Use side_effect to distinguish calls if needed, but here we'll just set it
        def mock_select(query):
            m = MagicMock()
            m.eq.return_value.order.return_value.limit.return_value.maybe_single.return_value.execute.return_value = mock_entry_resp
            m.eq.return_value.order.return_value.execute.return_value = mock_hist_resp
            return m
            
        mock_table.select.side_effect = mock_select
        
        await S.job_token_depletion_check(bot)
        
        # Verify 7-day alert sent
        bot.send_message.assert_called()
        msg = bot.send_message.call_args[1]["text"]
        print(f"PASS: 7-Day Alert Sent")
        assert "run out in about 7 days" in msg
        
        # Verify flag updated
        mock_table.update.assert_called_with({"alert_7d_sent": True})
        
        # ── SCENARIO 2: 7-Day Threshold (Deduplication Check) ────────────────
        bot.send_message.reset_mock()
        mock_table.update.reset_mock()
        entry_data["alert_7d_sent"] = True
        print("\nScenario 2: 7 days remaining, but flag is ALREADY TRUE...")
        await S.job_token_depletion_check(bot)
        bot.send_message.assert_not_called()
        print("PASS: No duplicate alert sent.")
        
        # ── SCENARIO 3: 3-Day Threshold ──────────────────────────────────────
        print("\nScenario 3: 3 days remaining...")
        entry_data.update({
            "id": "entry_3d",
            "units": 10.0,
            "alert_7d_sent": True,
            "alert_3d_sent": False
        })
        bot.send_message.reset_mock()
        await S.job_token_depletion_check(bot)
        msg = bot.send_message.call_args[1]["text"]
        print(f"PASS: 3-Day Alert Sent")
        assert "low -- 3 days remaining" in msg.replace("—", "--")
        mock_table.update.assert_called_with({"alert_3d_sent": True})

        # ── SCENARIO 4: 1-Day Threshold (Critical) ───────────────────────────
        print("\nScenario 4: 1 day remaining (Critical)...")
        entry_data.update({
            "id": "entry_1d",
            "units": 5.0,
            "alert_3d_sent": True,
            "alert_1d_sent": False
        })
        bot.send_message.reset_mock()
        await S.job_token_depletion_check(bot)
        msg = bot.send_message.call_args[1]["text"]
        print(f"PASS: 1-Day Alert Sent")
        assert "URGENT" in msg
        
        # ── SCENARIO 5: 1-Day Repeat Check ───────────────────────────────────
        print("\nScenario 5: 1 day remaining, day 2 (Flag already True)...")
        entry_data["alert_1d_sent"] = True 
        bot.send_message.reset_mock()
        await S.job_token_depletion_check(bot)
        bot.send_message.assert_called()
        print("PASS: 1-Day Alert repeats as expected.")

        # ── SCENARIO 6: Resolution (New Token Added) ────────────────────────
        print("\nScenario 6: New Token Added (Reset Cycle)...")
        new_entry = {
            "id": "entry_new",
            "units": 50.0,
            "purchase_date": datetime.now(timezone.utc).isoformat(),
            "alert_7d_sent": False,
            "alert_3d_sent": False,
            "alert_1d_sent": False
        }
        mock_entry_resp.data = new_entry
        mock_hist_resp.data = [new_entry, entry_data]
        
        bot.send_message.reset_mock()
        await S.job_token_depletion_check(bot)
        bot.send_message.assert_not_called()
        print("PASS: Cycle reset. No alerts for fresh token.")

    print("\nALL SIMULATIONS PASSED")

if __name__ == "__main__":
    try:
        asyncio.run(run_simulation())
    except Exception as e:
        print(f"\nSIMULATION FAILED: {e}")
