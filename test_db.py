
import apps.tg_bot.db as db
tid = "aea13d22-93c5-4942-b1f6-5febfead3a0c"
print(f"Checking statement for tenant: {tid}")
stmt = db.get_latest_statement(tid)
print(f"Statement: {stmt}")
