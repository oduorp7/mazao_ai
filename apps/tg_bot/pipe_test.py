"""
pipe_test.py — Zero-dependency Telegram connectivity proof.
Uses only stdlib urllib. No frameworks, no asyncio, no libraries.
"""
import json
import urllib.request
import time

# Read token directly
with open(".env") as f:
    for line in f:
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            TOKEN = line.strip().split("=", 1)[1]
            break

BASE = f"https://api.telegram.org/bot{TOKEN}"


def api(method, data=None):
    url = f"{BASE}/{method}"
    if data:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )
    else:
        req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())


def main():
    print(f"Token: ...{TOKEN[-6:]}")

    # 1. Verify identity
    me = api("getMe")
    print(f"1. Identity: @{me['result']['username']} (id={me['result']['id']})")

    # 2. Delete webhook
    wh = api("deleteWebhook", {"drop_pending_updates": True})
    print(f"2. Webhook cleared: {wh['ok']}")

    # 3. Poll for updates in a loop
    print("\n=== LISTENING FOR 120 SECONDS ===")
    print(">>> SEND /start TO THE BOT NOW <<<\n")

    offset = 0
    start = time.time()
    while time.time() - start < 120:
        try:
            result = api(f"getUpdates?offset={offset}&timeout=5")
            updates = result.get("result", [])

            if updates:
                for u in updates:
                    offset = u["update_id"] + 1
                    msg = u.get("message", {})
                    text = msg.get("text", "")
                    chat_id = msg.get("chat", {}).get("id")
                    user = msg.get("from", {}).get("first_name", "?")

                    print(f">>> RECEIVED: '{text}' from {user} (chat_id={chat_id})")

                    # Reply immediately
                    reply = api(
                        "sendMessage",
                        {
                            "chat_id": chat_id,
                            "text": f"✅ PIPE TEST SUCCESS!\n\nI received: '{text}'\nFrom: {user}\n\nThe connection is working. Starting full bot now.",
                        },
                    )
                    print(f"<<< REPLIED: ok={reply['ok']}")
                    print("\n✅ PROOF OF LIFE CONFIRMED. Exiting test.")
                    return True
            else:
                print(".", end="", flush=True)

        except Exception as e:
            print(f"\n!!! ERROR: {e}")
            time.sleep(2)

    print("\n\n❌ NO MESSAGES RECEIVED IN 120 SECONDS.")
    print("This means Telegram is not delivering updates to this token.")
    return False


if __name__ == "__main__":
    main()
