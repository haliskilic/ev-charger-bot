"""Print the chat id, topic (thread) id and user id from the bot's pending updates — first-time setup helper.

1. Create the bot with @BotFather and put the token into .env (TELEGRAM_BOT_TOKEN=...).
2. Add the bot to your group, open the topic where reports should go and send:  /start@your_bot_name
3. Run:  python -m tools.telegram_ids     (stop the bot service first; only one process may poll updates)
"""

from __future__ import annotations

import json
import os
import urllib.request

from evsarj import config


def main() -> None:
    config.load_env(config.BASE_DIR / ".env")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is missing from .env")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates?limit=100", timeout=20) as r:
        data = json.load(r)
    updates = data.get("result", [])
    if not updates:
        print("No updates. Send /start@your_bot_name in the target topic and run this again.")
        return
    for u in updates:
        m = u.get("message") or {}
        chat = m.get("chat", {})
        user = m.get("from", {})
        if not chat:
            continue
        print(f"chat: {chat.get('id')}  type={chat.get('type')}  title={chat.get('title')!r}  forum={chat.get('is_forum')}")
        print(f"  thread (topic) id: {m.get('message_thread_id') if m.get('is_topic_message') else '(General topic: leave TELEGRAM_THREAD_ID empty)'}")
        print(f"  from user id: {user.get('id')} ({user.get('first_name')})  text={m.get('text')!r}")
    print("\nPut these into .env as TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID and TELEGRAM_OWNER_ID.")


if __name__ == "__main__":
    main()
