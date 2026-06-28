
import sys, os
from dotenv import load_dotenv
load_dotenv('.env')
sys.path.insert(0, 'c:/Users/LENOVO/Documents/mazao_ai')
import asyncio
from unittest.mock import AsyncMock, MagicMock
from apps.tg_bot.handlers import awaiting_tokens

class MockMessage:
    def __init__(self, text):
        self.text = text

class MockUpdate:
    def __init__(self, text):
        self.message = MockMessage(text)
        self.effective_user = MagicMock(id=12345)
    async def get_bot(self):
        return MagicMock()

class MockContext:
    pass

async def _mock_reply(update, text, **kwargs):
    print('REPLY_TEXT:', text.replace('\n', '\\n'))

import apps.tg_bot.handlers
apps.tg_bot.handlers._reply = _mock_reply

async def run_tests():
    print('--- BP5 ---')
    await awaiting_tokens(MockUpdate('25.5 28/05/2026'), MockContext())
    print('--- BP6 ---')
    await awaiting_tokens(MockUpdate('25.5 28/06/2027'), MockContext())
    print('--- BP7 ---')
    await awaiting_tokens(MockUpdate('25.5 01/01/2025'), MockContext())

asyncio.run(run_tests())

