import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from apps.tg_bot import handlers
from apps.tg_bot import messages as M

class TestVATHygiene(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tid = 12345
        self.update = MagicMock()
        self.update.effective_user.id = self.tid
        self.update.effective_chat.id = self.tid
        self.update.effective_message = AsyncMock()
        self.update.effective_message.reply_text = AsyncMock()
        self.context = MagicMock()

    @patch("apps.tg_bot.db.get_tenant")
    @patch("apps.tg_bot.db.get_latest_statement")
    async def test_vat_unavailable_no_statement(self, mock_statement, mock_tenant):
        mock_tenant.return_value = {"id": "123", "telegram_id": self.tid}
        mock_statement.return_value = None

        await handlers.cmd_vat(self.update, self.context)
        
        self.update.effective_message.reply_text.assert_called_once()
        args, kwargs = self.update.effective_message.reply_text.call_args
        text = args[0]
        
        # Verify it returns safe unavailable state
        self.assertEqual(text, M.VAT_UNAVAILABLE)
        
        # Verify no hardcoded values appear
        self.assertNotIn("Taxable sales:      KES", text)
        self.assertNotIn("Output VAT (16%):   KES", text)
        
    @patch("apps.tg_bot.db.get_tenant")
    @patch("apps.tg_bot.db.get_latest_statement")
    async def test_vat_unavailable_even_with_statement(self, mock_statement, mock_tenant):
        mock_tenant.return_value = {"id": "123", "telegram_id": self.tid}
        mock_statement.return_value = {"total_inflows": 1000}

        await handlers.cmd_vat(self.update, self.context)
        
        self.update.effective_message.reply_text.assert_called_once()
        args, kwargs = self.update.effective_message.reply_text.call_args
        text = args[0]
        
        self.assertEqual(text, M.VAT_UNAVAILABLE)

if __name__ == "__main__":
    unittest.main()
