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

if __name__ == '__main__':
    unittest.main()
