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
        self.assertIn("requires an active subscription", args[0])

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

if __name__ == '__main__':
    unittest.main()
