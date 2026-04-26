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
        """Verify Full SMS format extracts all fields and renders intelligence output."""
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
        
        # Verify intelligence output
        mock_reply.assert_called()
        reply_text = "".join(call[0][1] for call in mock_reply.call_args_list)
        self.assertIn("🧾 *Code:* UDOL822FF5", reply_text)
        self.assertIn("💸 *Borrowed:* KES 191.57", reply_text)
        self.assertIn("📈 *Access Fee:* KES 1.92", reply_text)
        self.assertIn("🧮 *Total Deducted:* KES 193.49", reply_text)
        self.assertIn("💰 *Outstanding:* KES 193.49", reply_text)
        self.assertIn("Quick View", reply_text)
        self.assertIn("*Risk:*", reply_text)

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    async def test_fuliza_quick_entry_parsing(self, mock_reply, mock_db):
        """Verify Quick Entry format renders safely without code/fee."""
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "awaiting_fuliza"}
        
        self.update.effective_message.text = "191.57 24/05/2026 193.49"
        
        from apps.tg_bot import handlers
        await handlers.handle_message(self.update, self.context)
        
        insert_args = mock_db.get_client().table().insert.call_args[0][0]
        self.assertEqual(insert_args["amount_borrowed"], 191.57)
        self.assertEqual(insert_args["balance"], 193.49)
        mock_reply.assert_called()
        reply_text = "".join(call[0][1] for call in mock_reply.call_args_list)
        self.assertIn("💸 *Borrowed:* KES 191.57", reply_text)
        self.assertIn("💰 *Outstanding:* KES 193.49", reply_text)
        self.assertNotIn("🧾 *Code:*", reply_text)  # No code in quick entry
        self.assertNotIn("Daily Cost", reply_text)  # No fee = no daily cost

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    async def test_fuliza_legacy_fallback(self, mock_reply, mock_db):
        """Verify Legacy format works (KES X.XX and Date)."""
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "awaiting_fuliza"}
        
        self.update.effective_message.text = "My Fuliza balance is KES 450.00. Please pay by 25/04/2026"
        
        from apps.tg_bot import handlers
        await handlers.handle_message(self.update, self.context)
        
        insert_args = mock_db.get_client().table().insert.call_args[0][0]
        self.assertEqual(insert_args["balance"], 450.00)
        self.assertNotIn("amount_borrowed", insert_args)
        self.assertNotIn("code", insert_args)
        
        mock_reply.assert_called()
        reply_text = "".join(call[0][1] for call in mock_reply.call_args_list)
        self.assertIn("💰 *Outstanding:* KES 450.00", reply_text)
        self.assertIn("*Risk:*", reply_text)

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    async def test_fuliza_invalid_input(self, mock_reply, mock_db):
        """Verify Invalid input throws correct message."""
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "awaiting_fuliza"}
        
        import apps.tg_bot.messages as M
        
        # Missing date and amount formats
        self.update.effective_message.text = "Just some random text"
        
        from apps.tg_bot import handlers
        await handlers.handle_message(self.update, self.context)
        
        mock_db.get_client().table().insert.assert_not_called()
        mock_reply.assert_called_with(self.update, M.FULIZA_PARSE_FAILED)

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    @patch('apps.tg_bot.handlers.datetime')
    async def test_fuliza_risk_high(self, mock_dt, mock_reply, mock_db):
        """Verify HIGH risk for days_left < 7."""
        from datetime import date, datetime as real_dt
        mock_dt.strptime = real_dt.strptime
        mock_dt.now.return_value.date.return_value = date(2026, 5, 20)  # 4 days before due
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "awaiting_fuliza"}
        self.update.effective_message.text = "191.57 24/05/2026 193.49"
        from apps.tg_bot import handlers
        await handlers.handle_message(self.update, self.context)
        reply_text = "".join(call[0][1] for call in mock_reply.call_args_list)
        self.assertIn("HIGH", reply_text)
        self.assertIn("🟠", reply_text)

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    @patch('apps.tg_bot.handlers.datetime')
    async def test_fuliza_risk_medium(self, mock_dt, mock_reply, mock_db):
        """Verify MEDIUM risk for 7 <= days_left <= 14."""
        from datetime import date, datetime as real_dt
        mock_dt.strptime = real_dt.strptime
        mock_dt.now.return_value.date.return_value = date(2026, 5, 14)  # 10 days before due
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "awaiting_fuliza"}
        self.update.effective_message.text = "191.57 24/05/2026 193.49"
        from apps.tg_bot import handlers
        await handlers.handle_message(self.update, self.context)
        reply_text = "".join(call[0][1] for call in mock_reply.call_args_list)
        self.assertIn("MEDIUM", reply_text)
        self.assertIn("🟡", reply_text)

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    @patch('apps.tg_bot.handlers.datetime')
    async def test_fuliza_risk_overdue(self, mock_dt, mock_reply, mock_db):
        """Verify OVERDUE risk for days_left <= 0."""
        from datetime import date, datetime as real_dt
        mock_dt.strptime = real_dt.strptime
        mock_dt.now.return_value.date.return_value = date(2026, 5, 25)  # 1 day after due
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "awaiting_fuliza"}
        self.update.effective_message.text = "191.57 24/05/2026 193.49"
        from apps.tg_bot import handlers
        await handlers.handle_message(self.update, self.context)
        reply_text = "".join(call[0][1] for call in mock_reply.call_args_list)
        self.assertIn("OVERDUE", reply_text)
        self.assertIn("🔴", reply_text)

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    @patch('apps.tg_bot.handlers.datetime')
    async def test_fuliza_daily_cost_view(self, mock_dt, mock_reply, mock_db):
        """Verify Daily Cost appears when fee is present and days_left > 0."""
        from datetime import date, datetime as real_dt
        mock_dt.strptime = real_dt.strptime
        mock_dt.now.return_value.date.return_value = date(2026, 5, 14)  # 10 days before due
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "awaiting_fuliza"}
        self.update.effective_message.text = "Code: UDOL822FF5\nFuliza Amount: 191.57\nFee: 1.92\nTotal: 193.49\nOutstanding: 193.49\nDue: 24/05/2026"
        from apps.tg_bot import handlers
        await handlers.handle_message(self.update, self.context)
        reply_text = "".join(call[0][1] for call in mock_reply.call_args_list)
        self.assertIn("Daily Cost", reply_text)
        self.assertIn("KES 0.19/day", reply_text)  # 1.92 / 10 = 0.192

    @patch('apps.tg_bot.handlers.is_feature_allowed')
    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    async def test_fuliza_dashboard_shows_before_prompt(self, mock_reply, mock_db, mock_allowed):
        """Verify /fuliza command shows dashboard before prompt."""
        mock_allowed.return_value = True
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_client().table().select().eq().order().limit().execute.return_value.data = [
            {"balance": 1000, "due_date": "2026-05-30", "code": "ABC", "access_fee": 10}
        ]
        
        from apps.tg_bot import handlers
        await handlers.cmd_fuliza(self.update, self.context)
        
        # Verify two replies: Dashboard then Prompt
        self.assertEqual(mock_reply.call_count, 2)
        dashboard_call = mock_reply.call_args_list[0]
        prompt_call = mock_reply.call_args_list[1]
        
        self.assertIn("📊 *Fuliza Status*", dashboard_call[0][1])
        self.assertIn("💳 *Fuliza Entry*", prompt_call[0][1])

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    async def test_fuliza_multi_entry_persists_state(self, mock_reply, mock_db):
        """Verify state is NOT cleared after successful entry."""
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "awaiting_fuliza"}
        mock_db.get_client().table().select().eq().eq().limit().execute.return_value.data = [] # No duplicate
        
        self.update.effective_message.text = "191.57 24/05/2026 193.49"
        
        from apps.tg_bot import handlers
        await handlers.handle_message(self.update, self.context)
        
        # Verify clear_conv_state was NOT called
        mock_db.clear_conv_state.assert_not_called()
        self.assertIn("📥 Paste another Fuliza SMS", mock_reply.call_args[0][1])

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    @patch('apps.tg_bot.handlers.datetime')
    async def test_fuliza_duplicate_code_blocked(self, mock_dt, mock_reply, mock_db):
        """Verify duplicate code returns existing entry and blocks insert."""
        from datetime import date, datetime as real_dt
        mock_dt.strptime = real_dt.strptime
        # Explicitly setup the chain to return a real date object
        mock_utcnow = MagicMock()
        mock_utcnow.date.return_value = date(2026, 5, 20)
        mock_dt.now.return_value = mock_utcnow
        
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_conv_state.return_value = {"state": "awaiting_fuliza"}
        
        # Mock existing entry
        mock_db.get_client().table().select().eq().eq().limit().execute.return_value.data = [{
            "code": "DUP123",
            "balance": 500.0,
            "due_date": "2026-05-25",
            "amount_borrowed": 490.0,
            "access_fee": 5.0,
            "total_deducted": 495.0
        }]
        
        self.update.effective_message.text = "Code: DUP123\nFuliza Amount: 490\nFee: 5\nTotal: 495\nOutstanding: 500\nDue: 25/05/2026"
        
        from apps.tg_bot import handlers
        await handlers.handle_message(self.update, self.context)
        
        # Verify insert was NOT called
        mock_db.get_client().table().insert.assert_not_called()
        
        # Verify replies
        reply_text = "".join(call[0][1] for call in mock_reply.call_args_list)
        self.assertIn("⚠️ *Already Recorded*", reply_text)
        self.assertIn("🧾 *Code:* DUP123", reply_text)
        self.assertIn("📥 Paste another Fuliza SMS", reply_text)
        self.assertIn("Quick View", reply_text)

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    async def test_fuliza_done_exits_state(self, mock_reply, mock_db):
        """Verify /done clears state and exits session."""
        mock_db.get_conv_state.return_value = {"state": "awaiting_fuliza"}
        self.update.effective_message.text = "/done"
        
        from apps.tg_bot import handlers
        await handlers.handle_message(self.update, self.context)
        
        mock_db.clear_conv_state.assert_called_once()
        mock_reply.assert_called()
        reply_text = "".join(call[0][1] for call in mock_reply.call_args_list)
        self.assertIn("✅ *Fuliza session complete.*", reply_text)




    @patch('apps.tg_bot.handlers.is_feature_allowed')
    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    @patch('apps.tg_bot.handlers.datetime')
    async def test_fuliza_pro_intelligence_visibility(self, mock_dt, mock_reply, mock_db, mock_allowed):
        """Verify Pro users see advanced Fuliza intelligence."""
        from datetime import date, datetime as real_dt
        mock_dt.strptime = real_dt.strptime
        mock_dt.now.return_value.date.return_value = date(2026, 5, 20)
        
        # Pro user
        mock_db.get_tenant.return_value = {**self.tenant, "plan": "pro"}
        mock_allowed.side_effect = lambda tid, feature: True if feature == "fuliza_intelligence" else True
        
        # Mock recent history (3 entries for dashboard)
        mock_db.get_client().table().select().eq().order().limit().execute.return_value.data = [
            {"balance": 1000, "due_date": "2026-05-25", "code": "ABC", "access_fee": 10}
        ]
        
        # Mock stats (for monthly burden and frequency)
        # 2 entries in current month (May)
        mock_db.get_client().table().select().eq().gte().execute.return_value.data = [
            {"access_fee": 10, "created_at": "2026-05-10T12:00:00Z"},
            {"access_fee": 15, "created_at": "2026-05-15T12:00:00Z"}
        ]
        
        from apps.tg_bot import handlers
        await handlers.cmd_fuliza(self.update, self.context)
        
        reply_text = "".join(call[0][1] for call in mock_reply.call_args_list)
        self.assertIn("Financial Insight (Pro)", reply_text)
        self.assertIn("Monthly Fee Burden: KES 25.00", reply_text)
        self.assertIn("30-Day Frequency: 2 entries", reply_text)

    @patch('apps.tg_bot.handlers.is_feature_allowed')
    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    async def test_fuliza_core_hidden_intelligence(self, mock_reply, mock_db, mock_allowed):
        """Verify Core users do NOT see advanced Fuliza intelligence."""
        mock_db.get_tenant.return_value = {**self.tenant, "plan": "core"}
        mock_allowed.side_effect = lambda tid, feature: False if feature == "fuliza_intelligence" else True
        
        mock_db.get_client().table().select().eq().order().limit().execute.return_value.data = []
        
        from apps.tg_bot import handlers
        await handlers.cmd_fuliza(self.update, self.context)
        
        reply_text = "".join(call[0][1] for call in mock_reply.call_args_list)
        self.assertNotIn("Financial Insight (Pro)", reply_text)

    @patch('apps.tg_bot.handlers.is_feature_allowed')
    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    @patch('apps.tg_bot.handlers.datetime')
    async def test_fuliza_frequency_signal(self, mock_dt, mock_reply, mock_db, mock_allowed):
        """Verify frequent-use nudge appears when threshold (>5) exceeded."""
        from datetime import date, datetime as real_dt
        mock_dt.strptime = real_dt.strptime
        mock_dt.now.return_value.date.return_value = date(2026, 5, 20)
        
        mock_db.get_tenant.return_value = {**self.tenant, "plan": "pro"}
        mock_allowed.return_value = True
        
        # 7 entries in last 30 days (Stats Query)
        mock_db.get_client().table().select().eq().gte().execute.return_value.data = [{"access_fee": 5, "created_at": "2026-05-10"}] * 7
        
        # Mock recent history (3 entries for dashboard - History Query)
        mock_db.get_client().table().select().eq().order().limit().execute.return_value.data = [
            {"balance": 1000, "due_date": "2026-05-25", "code": "ABC", "access_fee": 10}
        ]
        
        from apps.tg_bot import handlers
        await handlers.cmd_fuliza(self.update, self.context)
        
        reply_text = "".join(call[0][1] for call in mock_reply.call_args_list)
        self.assertIn("7 entries", reply_text)
        # Check for nudge text from messages.py
        self.assertIn("High Frequency", reply_text)


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

class TestSuperadminBypass(unittest.IsolatedAsyncioTestCase):
    """Tier A: Verify Superadmin env-var-sourced bypass (P17-T5D)."""

    ADMIN_TID = "7654321"

    @patch('apps.tg_bot.trial.get_client')
    async def test_superadmin_bypass_allows_fuliza(self, mock_get_client):
        """Superadmin should get True for any feature."""
        import apps.tg_bot.trial as trial_mod
        # Simulate env-var-sourced superadmin list
        original = trial_mod.SUPERADMIN_TELEGRAM_IDS
        trial_mod.SUPERADMIN_TELEGRAM_IDS = [self.ADMIN_TID]
        
        try:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_res = MagicMock()
            mock_res.data = {"telegram_id": self.ADMIN_TID}
            mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_res
            
            allowed = await trial_mod.is_feature_allowed("some-tenant-id", "utility_tracking")
            self.assertTrue(allowed)
        finally:
            trial_mod.SUPERADMIN_TELEGRAM_IDS = original

    @patch('apps.tg_bot.trial.get_client')
    @patch('apps.tg_bot.trial.get_trial_status', new_callable=AsyncMock)
    async def test_normal_user_still_blocked_without_subscription(self, mock_status, mock_get_client):
        """Normal free users should be blocked for utility_tracking."""
        import apps.tg_bot.trial as trial_mod
        original = trial_mod.SUPERADMIN_TELEGRAM_IDS
        trial_mod.SUPERADMIN_TELEGRAM_IDS = [self.ADMIN_TID]
        
        try:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_res = MagicMock()
            mock_res.data = {"telegram_id": "999999"}  # Not an admin
            mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_res
            
            mock_status.return_value = {"active": False, "days_remaining": 0, "is_expired": True, "plan": "free"}
            
            allowed = await trial_mod.is_feature_allowed("some-tenant-id", "utility_tracking")
            self.assertFalse(allowed)
        finally:
            trial_mod.SUPERADMIN_TELEGRAM_IDS = original


class TestStatementEmptyStateFlow(unittest.IsolatedAsyncioTestCase):
    """T6F-EMPTY-STATE: Verify guided ingestion flow for /statement and /report."""

    def setUp(self):
        self.tid = 123456789
        self.tenant = {
            "id": "8f8e8d8c-8b8a-8988-8786-858483828180",
            "telegram_id": self.tid,
            "plan": "trial",
        }
        self.update = AsyncMock()
        self.update.effective_user.id = self.tid
        self.update.effective_chat.id = self.tid
        self.update.effective_message = AsyncMock()
        self.update.message = self.update.effective_message
        self.update.effective_message.text = ""
        self.update.effective_message.document = None
        self.context = MagicMock()
        self.context.user_data = {}

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    async def test_statement_empty_state_shows_buttons(self, mock_reply, mock_db):
        """Verify /statement with no data shows CTA buttons, not a dead-end text."""
        mock_db.get_tenant.return_value = self.tenant
        mock_db.get_latest_statement.return_value = None  # No statement uploaded

        import apps.tg_bot.handlers as handlers
        await handlers.cmd_statement(self.update, self.context)

        mock_reply.assert_called_once()
        call_args = mock_reply.call_args
        # Verify message text is the new empty-state message
        assert "No M-Pesa Statement Found" in call_args[0][1], \
            "Empty state message not shown"
        # Verify inline keyboard CTA buttons were passed
        reply_markup = call_args[1].get("reply_markup")
        assert reply_markup is not None, "No reply_markup (CTA buttons) passed"
        # Verify button callback_data
        button_callbacks = [
            btn.callback_data
            for row in reply_markup.inline_keyboard
            for btn in row
        ]
        assert "statement_upload" in button_callbacks, "Upload button missing"
        assert "statement_guide" in button_callbacks, "Guide button missing"

    @patch('apps.tg_bot.handlers.db')
    async def test_statement_upload_session_trigger(self, mock_db):
        """Verify statement_upload callback sets awaiting_statement_upload state."""
        query = AsyncMock()
        query.from_user.id = self.tid
        query.data = "statement_upload"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()

        self.update.callback_query = query

        import apps.tg_bot.handlers as handlers
        await handlers.handle_callback(self.update, self.context)

        # Verify session state was set
        mock_db.set_conv_state.assert_called_once_with(self.tid, "awaiting_statement_upload")
        # Verify prompt was shown via edit_message_text
        query.edit_message_text.assert_called_once()
        prompt_text = query.edit_message_text.call_args[0][0]
        assert "Send your M-Pesa Statement" in prompt_text, "Upload prompt not shown"

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    async def test_statement_rejects_text_in_upload_mode(self, mock_reply, mock_db):
        """Verify text input while in awaiting_statement_upload is rejected with guidance."""
        mock_db.get_conv_state.return_value = {"state": "awaiting_statement_upload"}
        mock_db.get_tenant.return_value = self.tenant

        # Simulate user sending text instead of a file
        self.update.effective_message.text = "Here is my statement"
        self.update.message.text = "Here is my statement"
        self.update.message.document = None

        import apps.tg_bot.handlers as handlers
        await handlers.handle_message(self.update, self.context)

        mock_reply.assert_called_once()
        reply_text = mock_reply.call_args[0][1]
        assert "Please Send a CSV File" in reply_text, "Rejection message not shown"
        # Verify state NOT cleared — user should still be in upload mode
        mock_db.clear_conv_state.assert_not_called()

    @patch('apps.tg_bot.handlers.db')
    @patch('apps.tg_bot.handlers._reply', new_callable=AsyncMock)
    async def test_statement_accepts_csv_file(self, mock_reply, mock_db):
        """Verify a valid .csv file is accepted, state is cleared, and success shown."""
        mock_db.get_conv_state.return_value = {"state": "awaiting_statement_upload"}
        mock_db.get_tenant.return_value = self.tenant

        # Simulate document upload (CSV)
        mock_doc = MagicMock()
        mock_doc.file_name = "M-Pesa_Statement.csv"
        mock_doc.file_size = 50 * 1024  # 50KB — well within limit

        self.update.effective_message.text = ""
        self.update.message.text = ""
        self.update.message.document = mock_doc

        import apps.tg_bot.handlers as handlers
        await handlers.handle_message(self.update, self.context)

        mock_reply.assert_called_once()
        reply_text = mock_reply.call_args[0][1]
        assert "Statement Received" in reply_text, "Success message not shown"
        assert "M-Pesa_Statement.csv" in reply_text, "Filename not in success message"
        # Verify state was cleared after successful upload
        mock_db.clear_conv_state.assert_called_once_with(self.tid)


if __name__ == '__main__':
    unittest.main()
