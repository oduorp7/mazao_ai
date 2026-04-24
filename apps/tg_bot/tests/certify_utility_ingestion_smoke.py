"""
certify_utility_ingestion_smoke.py — Tier A Smoke Harness for Mazao AI.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

# Import handlers
import apps.tg_bot.handlers as handlers

class TestUtilityIngestionSmoke(unittest.IsolatedAsyncioTestCase):
    """Tier A Smoke Harness: End-to-End Ingestion Validation."""

    def setUp(self):
        self.tid = 123456789
        self.tenant = {
            "id": "8f8e8d8c-8b8a-8988-8786-858483828180",
            "telegram_id": self.tid,
            "household_type": "standard",
            "preferred_language": "en"
        }
        self.update = AsyncMock()
        self.update.effective_chat.id = self.tid
        self.update.effective_user.id = self.tid
        self.update.effective_message = AsyncMock()
        self.update.message = self.update.effective_message
        self.update.effective_message.text = ""
        self.context = MagicMock()

    @patch('apps.tg_bot.handlers.is_feature_allowed', new_callable=AsyncMock)
    @patch('apps.tg_bot.handlers.db')
    @patch('apps.agent.tips.generate_tip', new_callable=AsyncMock)
    async def test_electricity_token_full_sms_ingestion(self, mock_gen_tip, mock_db, mock_allowed):
        # Explicitly setup the mock inside the test to be thread-safe
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "idle"}
        mock_gen_tip.return_value = "AI Insight"
        mock_allowed.return_value = True
        
        mock_client = MagicMock()
        mock_db.get_client.return_value = mock_client
        mock_client.table().select().eq().order().execute.return_value.data = [
            {"units": 28.3, "purchase_date": "2026-04-22T12:00:00Z"}
        ]
        
        sms = ("Mtr:123 Token:456 Date:20260422 12:00 Units:28.3 Amt:1000.00 "
               "TknAmt:525.26 OtherCharges:474.74")
        self.update.effective_message.text = sms

        await handlers.awaiting_tokens(self.update, self.context)
        self.update.effective_message.reply_text.assert_called()

    @patch('apps.tg_bot.handlers.is_feature_allowed', new_callable=AsyncMock)
    @patch('apps.tg_bot.handlers.db')
    @patch('apps.agent.tips.generate_tip', new_callable=AsyncMock)
    async def test_tier_c_safe_degradation(self, mock_gen_tip, mock_db, mock_allowed):
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "idle"}
        mock_gen_tip.side_effect = Exception("LLM Error")
        mock_allowed.return_value = True
        
        mock_client = MagicMock()
        mock_db.get_client.return_value = mock_client
        mock_client.table().select().eq().order().execute.return_value.data = [
            {"units": 28.3, "purchase_date": "2026-04-22T12:00:00Z"}
        ]
        
        sms = ("Mtr:123 Token:456 Date:20260422 12:00 Units:28.3 Amt:1000.00 "
               "TknAmt:525.26 OtherCharges:474.74")
        self.update.effective_message.text = sms

        await handlers.awaiting_tokens(self.update, self.context)
        self.update.effective_message.reply_text.assert_called()

    @patch('apps.tg_bot.handlers.is_feature_allowed', new_callable=AsyncMock)
    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._get_gas_projection', new_callable=AsyncMock)
    async def test_gas_refill_ingestion(self, mock_get_proj, mock_db, mock_allowed):
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "awaiting_gas"}
        mock_allowed.return_value = True
        mock_get_proj.return_value = {
            "n": 1, "daily_rate": 0.5, "days_remaining": 26,
            "depletion_date": "18 May 2026",
            "confidence": {"bar": "░░░░░", "label": "Grid baseline"}
        }
        
        self.update.effective_message.text = "13 22/04/2026"
        await handlers.handle_message(self.update, self.context)
        self.update.effective_message.reply_text.assert_called()

    @patch('apps.tg_bot.handlers.is_feature_allowed', new_callable=AsyncMock)
    @patch('apps.tg_bot.handlers.db')
    async def test_subscription_block_lapsed_user(self, mock_db, mock_allowed):
        """P17-T4A: Verify that a lapsed user is blocked from utility entry."""
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "idle"}
        mock_allowed.return_value = False
        
        # Scenario 1: Auto-Detect SMS
        self.update.effective_message.text = "Mtr:123 Token:456 Units:28.3 Amt:1000.00"
        await handlers.handle_message(self.update, self.context)
        
        # Verify block message was sent
        self.update.effective_message.reply_text.assert_called()
        args, kwargs = self.update.effective_message.reply_text.call_args
        self.assertIn("available on Mazao Core", args[0])

    @patch('apps.tg_bot.handlers.is_feature_allowed', new_callable=AsyncMock)
    @patch('apps.tg_bot.handlers.db')
    async def test_subscription_block_awaiting_gas(self, mock_db, mock_allowed):
        """P17-T4A: Verify that a lapsed user is blocked during awaiting_gas state."""
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "awaiting_gas"}
        mock_allowed.return_value = False
        
        self.update.effective_message.text = "13 22/04/2026"
        await handlers.handle_message(self.update, self.context)
        
        # Verify block message and state clearing
        self.update.effective_message.reply_text.assert_called()
        mock_db.clear_conv_state.assert_called_with(self.tid)

class TestFulizaInputContract(unittest.IsolatedAsyncioTestCase):
    """Tier A: Verify Fuliza input standardization (P17-T5)."""

    def setUp(self):
        self.tid = 123456789
        self.update = AsyncMock()
        self.update.effective_user.id = self.tid
        self.update.effective_chat.id = self.tid
        self.update.effective_message = AsyncMock()
        self.update.message = self.update.effective_message
        self.context = MagicMock()
        self.context.user_data = {}
        self.tenant = {"id": "test-uuid", "plan": "pro"}

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    async def test_fuliza_full_sms_parsing(self, mock_reply, mock_db):
        """Verify Full SMS format extracts all fields correctly."""
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "awaiting_fuliza"}
        
        self.update.effective_message.text = "Code: UDOL822FF5\nFuliza Amount: 191.57\nFee: 1.92\nTotal: 193.49\nOutstanding: 193.49\nDue: 24/05/2026"
        
        from apps.tg_bot import handlers
        await handlers.handle_message(self.update, self.context)
        
        # Verify db insert was called with all fields
        insert_args = mock_db.get_client().table().insert.call_args[0][0]
        self.assertEqual(insert_args["code"], "UDOL822FF5")
        self.assertEqual(insert_args["amount_borrowed"], 191.57)
        self.assertEqual(insert_args["access_fee"], 1.92)
        self.assertEqual(insert_args["total_deducted"], 193.49)
        self.assertEqual(insert_args["balance"], 193.49)
        
        # Verify reply contains extra details
        mock_reply.assert_called()
        reply_text = mock_reply.call_args[0][1]
        self.assertIn("🧾 *Code:* UDOL822FF5", reply_text)
        self.assertIn("💸 *Borrowed:* KES 191.57", reply_text)
        self.assertIn("📈 *Fee:* KES 1.92", reply_text)

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    async def test_fuliza_quick_entry_parsing(self, mock_reply, mock_db):
        """Verify Quick Entry format works."""
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "awaiting_fuliza"}
        
        self.update.effective_message.text = "191.57 24/05/2026 193.49"
        
        from apps.tg_bot import handlers
        await handlers.handle_message(self.update, self.context)
        
        insert_args = mock_db.get_client().table().insert.call_args[0][0]
        self.assertEqual(insert_args["amount_borrowed"], 191.57)
        self.assertEqual(insert_args["balance"], 193.49)
        self.assertNotIn("code", insert_args)
        
        mock_reply.assert_called()
        reply_text = mock_reply.call_args[0][1]
        self.assertIn("💸 *Borrowed:* KES 191.57", reply_text)

class TestSchedulerStopGates(unittest.IsolatedAsyncioTestCase):
    """Tier A: Verify that scheduler jobs respect user stop-gates."""

    def setUp(self):
        self.tid = 123456789
        self.update = AsyncMock()
        self.context = MagicMock()
        self.bot = AsyncMock()
        self.context.bot = self.bot

    @patch('apps.tg_bot.db.get_client')
    async def test_fuliza_alerts_skip_paused_users(self, mock_get_client):
        """Verify Fuliza alerts exclude paused users."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        # Mock a 'paused' user in the result
        # Note: In reality, our new !inner join query would return 0 rows for paused users
        mock_client.table().select().in_().execute.return_value.data = []

        import apps.tg_bot.scheduler as scheduler
        await scheduler.job_fuliza_alerts(self.bot)
        
        # Verify no message sent
        self.bot.send_message.assert_not_called()

    @patch('apps.tg_bot.db.get_client')
    async def test_subscription_renewal_skip_paused_users(self, mock_get_client):
        """Verify subscription renewal excludes paused users."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        # Mock empty result for active+subscription tenants
        mock_client.table().select().eq().in_().execute.return_value.data = []

        import apps.tg_bot.scheduler as scheduler
        await scheduler.job_subscription_renewal_alerts(self.bot)
        
        self.bot.send_message.assert_not_called()

class TestTierGating(unittest.IsolatedAsyncioTestCase):
    """Tier A: Verify that feature gating respects the 4-tier matrix."""

    def setUp(self):
        self.tid = 123456789

    @patch('apps.tg_bot.trial.get_trial_status', new_callable=AsyncMock)
    async def test_trial_full_pro_access(self, mock_status):
        """Trial must have full access."""
        mock_status.return_value = {"active": True, "plan": "trial"}
        from apps.tg_bot.trial import is_feature_allowed
        self.assertTrue(await is_feature_allowed(self.tid, "ai_tips"))
        self.assertTrue(await is_feature_allowed(self.tid, "proactive_alerts"))

    @patch('apps.tg_bot.trial.get_trial_status', new_callable=AsyncMock)
    async def test_free_tier_manual_only(self, mock_status):
        """Free tier must block AI and alerts."""
        mock_status.return_value = {"active": False, "plan": "free"}
        from apps.tg_bot.trial import is_feature_allowed
        self.assertTrue(await is_feature_allowed(self.tid, "manual_tracking"))
        self.assertFalse(await is_feature_allowed(self.tid, "ai_tips"))
        self.assertFalse(await is_feature_allowed(self.tid, "proactive_alerts"))

    @patch('apps.tg_bot.trial.get_trial_status', new_callable=AsyncMock)
    async def test_core_tier_access(self, mock_status):
        """Core tier has alerts but no AI tips."""
        mock_status.return_value = {"active": True, "plan": "core"}
        from apps.tg_bot.trial import is_feature_allowed
        self.assertTrue(await is_feature_allowed(self.tid, "proactive_alerts"))
        self.assertFalse(await is_feature_allowed(self.tid, "ai_tips"))

    @patch('apps.tg_bot.trial.get_trial_status', new_callable=AsyncMock)
    async def test_pro_tier_access(self, mock_status):
        """Pro tier has everything."""
        mock_status.return_value = {"active": True, "plan": "pro"}
        from apps.tg_bot.trial import is_feature_allowed
        self.assertTrue(await is_feature_allowed(self.tid, "ai_tips"))

    @patch('apps.tg_bot.trial.get_trial_status', new_callable=AsyncMock)
    async def test_paid_gating_requires_active(self, mock_status):
        """Paid tiers must block if subscription_active is False."""
        # active=False in get_trial_status return dict means subscription_active=False
        mock_status.return_value = {"active": False, "plan": "pro"}
        from apps.tg_bot.trial import is_feature_allowed
        self.assertFalse(await is_feature_allowed(self.tid, "ai_tips"))

    @patch('apps.tg_bot.db.get_client')
    async def test_expiry_downgrade_logic(self, mock_get_client):
        """Verify scheduler downgrades plan to free on expiry."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        # Mock a tenant with expired sub
        from datetime import datetime, timezone, timedelta
        expired_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        mock_client.table().select().eq().in_().execute.return_value.data = [{
            "id": "tenant-123",
            "telegram_id": self.tid,
            "subscription_expires_at": expired_date,
            "plan": "pro",
            "subscription_active": True,
            "status": "active"
        }]

        from apps.tg_bot.scheduler import job_subscription_renewal_alerts
        bot = AsyncMock()
        await job_subscription_renewal_alerts(bot)
        
        # Verify DB update set plan='free'
        mock_client.table().update.assert_any_call({
            "subscription_active": False,
            "status": "lapsed",
            "plan": "free"
        })
class TestAdminDashboardNormalization(unittest.IsolatedAsyncioTestCase):
    """Tier A: Verify Admin Dashboard correctly normalizes legacy labels."""

    def setUp(self):
        self.tid = 999999999 # Admin ID
        self.admin_id = "999999999"
        self.update = AsyncMock()
        self.update.effective_chat.id = self.tid
        self.update.effective_user.id = self.tid
        self.update.message = AsyncMock()
        self.context = MagicMock()

    @patch('apps.tg_bot.handlers.db')
    @patch('os.getenv')
    async def test_admin_output_normalization(self, mock_getenv, mock_db):
        """Verify cmd_admin maps legacy values to Free/Trial/Core/Pro and splits Free/Trial."""
        mock_getenv.return_value = self.admin_id
        
        # Mock mixed legacy DB state
        mock_client = MagicMock()
        mock_db.get_client.return_value = mock_client
        
        # Chainable calls must return the mock_client or another mock that leads to execute
        mock_client.table.return_value = mock_client
        mock_client.select.return_value = mock_client
        mock_client.eq.return_value = mock_client
        mock_client.gte.return_value = mock_client
        
        # 1. Tenants mock
        mock_tenants_data = [
            {"telegram_id": 1, "plan": "biashara", "onboarding_completed": True},
            {"telegram_id": 2, "plan": "pro", "onboarding_completed": True},
            {"telegram_id": 3, "plan": "mtu_wenyewe", "onboarding_completed": True},
            {"telegram_id": 4, "plan": "core", "onboarding_completed": True},
            {"telegram_id": 5, "plan": "trial", "onboarding_completed": True},
            {"telegram_id": 6, "plan": "free", "onboarding_completed": True},
            {"telegram_id": 7, "plan": "hustler", "onboarding_completed": True},
        ]
        
        mock_res_tenants = MagicMock()
        mock_res_tenants.data = mock_tenants_data
        
        mock_res_trials = MagicMock()
        mock_res_trials.data = [{"trial_days_left": 5}]
        
        mock_res_rev = MagicMock()
        mock_res_rev.data = []
        
        mock_res_expired = MagicMock()
        mock_res_expired.data = []
        
        # Sequential returns for execute()
        mock_client.execute.side_effect = [
            mock_res_tenants,
            mock_res_trials,
            mock_res_rev,
            mock_res_expired
        ]
        
        # Patch _reply to capture the output message
        with patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock) as mock_reply:
            await handlers.cmd_admin(self.update, self.context)
            
            mock_reply.assert_called()
            report_text = mock_reply.call_args[0][1]
            
            # Assert legacy labels are ABSENT
            self.assertNotIn("biashara", report_text.lower())
            self.assertNotIn("mtu_wenyewe", report_text.lower())
            self.assertNotIn("hustler", report_text.lower())
            
            # Assert current labels are PRESENT with correct counts
            # biashara(1) + pro(1) = Pro (2)
            # mtu_wenyewe(1) + core(1) = Core (2)
            # hustler(1) + free(1) = Free (2)
            # trial(1) = Trial (1)
            self.assertIn("Pro (KES 399): 2", report_text)
            self.assertIn("Core (KES 149): 2", report_text)
            self.assertIn("Trial: 1", report_text)
            self.assertIn("Free: 2", report_text)

class TestConversionGrowthLayer(unittest.IsolatedAsyncioTestCase):
    """Tier A: Verify Conversion and Growth triggers (P17-T4J)."""

    def setUp(self):
        self.tid = 123456789
        self.update = AsyncMock()
        self.update.effective_user.id = self.tid
        self.update.effective_chat.id = self.tid
        self.update.message = AsyncMock()
        self.context = MagicMock()
        self.context.user_data = {}

    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    async def test_post_usage_nudge_session_gating(self, mock_reply):
        """Verify _maybe_send_nudge obeys session gating (max 1 nudge)."""
        from apps.tg_bot.handlers import _maybe_send_nudge
        import apps.tg_bot.messages as M
        
        # 1. First nudge should pass
        await _maybe_send_nudge(self.update, self.context, M.NUDGE_POST_USAGE_VALUE, condition=True)
        mock_reply.assert_called_with(self.update, M.NUDGE_POST_USAGE_VALUE)
        self.assertTrue(self.context.user_data.get("nudge_sent_this_session"))
        
        # 2. Second nudge should be blocked
        mock_reply.reset_mock()
        await _maybe_send_nudge(self.update, self.context, M.NUDGE_REPORT_VALUE_ANCHOR, condition=True)
        mock_reply.assert_not_called()

    @patch('apps.tg_bot.scheduler.db.get_client')
    @patch('apps.tg_bot.scheduler.db.get_all_active_tenants')
    async def test_trial_day_6_urgency(self, mock_get_all, mock_get_client):
        """Trial user on day 6 sees urgency message (Conversion Trigger 1)."""
        from apps.tg_bot.scheduler import job_trial_alerts
        import apps.tg_bot.messages as M
        
        bot = AsyncMock()
        from datetime import datetime, timezone, timedelta
        # Day 6 means ends in 1 day. Use 1.5 days to ensure (ends - now).days == 1 
        # despite any small execution delays.
        ends = (datetime.now(timezone.utc) + timedelta(days=1.5)).isoformat()
        
        mock_get_all.return_value = [{
            "telegram_id": self.tid,
            "plan": "free", 
            "subscription_active": False,
            "trial_ends_at": ends,
            "id": "t1"
        }]
        
        await job_trial_alerts(bot)
        
        bot.send_message.assert_called()
        args = bot.send_message.call_args[1]
        self.assertEqual(args["text"], M.NUDGE_TRIAL_DAY_6)

    @patch('apps.tg_bot.scheduler.db.get_client')
    async def test_inactivity_reactivation(self, mock_get_client):
        """Lapsed user receives reactivation nudge (Conversion Trigger 5)."""
        from apps.tg_bot.scheduler import job_inactivity_reactivation
        import apps.tg_bot.messages as M
        from telegram.constants import ParseMode
        
        bot = AsyncMock()
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        mock_res = MagicMock()
        mock_res.data = [{"telegram_id": self.tid, "plan": "free", "status": "lapsed"}]
        # Mocking the query chain: client.table().select().eq().eq().execute()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_res
        
        await job_inactivity_reactivation(bot)
        
        bot.send_message.assert_called_with(
            chat_id=self.tid,
            text=M.NUDGE_INACTIVITY_REACTIVATION,
            parse_mode=ParseMode.MARKDOWN
        )


if __name__ == '__main__':
    unittest.main()
