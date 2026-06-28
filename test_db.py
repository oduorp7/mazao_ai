
import sys, os
from dotenv import load_dotenv
load_dotenv('c:/Users/LENOVO/Documents/mazao_ai/apps/tg_bot/.env')
sys.path.insert(0, 'c:/Users/LENOVO/Documents/mazao_ai')
import asyncio
from apps.tg_bot.db import get_client

async def test():
    try:
        get_client().table('token_entries').insert({
            'tenant_id': '00000000-0000-0000-0000-000000000000',
            'units': 1,
            'purchase_date': '2026-05-28',
            'amount_paid': None
        }).execute()
    except Exception as e:
        print('EXC_TYPE:', type(e))
        print('EXC_STR:', str(e))
        print('EXC_DIR:', dir(e))
        try:
            print('EXC_DETAILS:', e.details)
        except:
            pass
        try:
            print('EXC_MESSAGE:', e.message)
        except:
            pass

asyncio.run(test())

