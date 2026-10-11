"""Access control: the bot must ignore every chat except the configured group and accept setting changes only from the owner."""

from __future__ import annotations

import asyncio
import types
import unittest
from unittest import mock

from evsarj import telegram_bot as tg

GROUP = -1001234567890
OWNER = 111
STRANGER = 222


class FakeApp:
    def __init__(self):
        self.sec = types.SimpleNamespace(tg_chat_id=GROUP, tg_owner_id=OWNER, tg_thread_id=5)
        self.R = types.SimpleNamespace(L=lambda key, **kw: key, tariff_cmd=lambda: "tariff_text", settings_cmd=lambda: "settings_text")
        self.db = mock.MagicMock()
        self.calls: list[str] = []

    def reload_settings(self):
        self.calls.append("reload")


def update(chat_id: int, user_id: int, text: str = "/status", topic: bool = True):
    msg = types.SimpleNamespace(text=text, message_thread_id=5 if topic else None, is_topic_message=topic)
    return types.SimpleNamespace(
        effective_message=msg,
        effective_chat=types.SimpleNamespace(id=chat_id, type="supergroup"),
        effective_user=types.SimpleNamespace(id=user_id),
        my_chat_member=None,
    )


class AccessControlTests(unittest.TestCase):
    def run_handler(self, fn, upd, app=None, args=None):
        app = app or FakeApp()
        replies: list[str] = []

        async def fake_reply(_app, _upd, text, document=None):
            replies.append(text)

        with mock.patch.object(tg, "reply", fake_reply):
            handler = tg._wrap(app, fn)
            ctx = types.SimpleNamespace(args=args or [])
            asyncio.run(handler(upd, ctx))
        return replies, app

    def test_private_chat_is_ignored(self):
        called = []

        async def fn(app, upd, ctx):
            called.append(1)
            return "x"

        replies, _ = self.run_handler(fn, update(chat_id=STRANGER, user_id=STRANGER, topic=False))
        self.assertEqual(called, [])
        self.assertEqual(replies, [])

    def test_other_group_is_ignored(self):
        called = []

        async def fn(app, upd, ctx):
            called.append(1)
            return "x"

        replies, _ = self.run_handler(fn, update(chat_id=-1009999999999, user_id=OWNER))
        self.assertEqual(called, [])
        self.assertEqual(replies, [])

    def test_configured_group_is_answered(self):
        async def fn(app, upd, ctx):
            return "answer"

        replies, _ = self.run_handler(fn, update(chat_id=GROUP, user_id=STRANGER))
        self.assertEqual(replies, ["answer"])

    def test_settings_change_requires_owner(self):
        replies, app = self.run_handler(tg.cmd_settings, update(chat_id=GROUP, user_id=STRANGER), args=["live", "3"])
        self.assertEqual(replies, ["settings_owner_only"])
        app.db.set_setting.assert_not_called()

    def test_settings_change_by_owner(self):
        replies, app = self.run_handler(tg.cmd_settings, update(chat_id=GROUP, user_id=OWNER), args=["live", "3"])
        app.db.set_setting.assert_called_with("live_status_min", "3")
        self.assertIn("reload", app.calls)

    def test_tariff_change_requires_owner(self):
        replies, app = self.run_handler(tg.cmd_tariff, update(chat_id=GROUP, user_id=STRANGER), args=["single", "0.3"])
        self.assertEqual(replies, ["tariff_owner_only"])
        app.db.set_setting.assert_not_called()

    def test_language_change_requires_owner(self):
        replies, app = self.run_handler(tg.cmd_language, update(chat_id=GROUP, user_id=STRANGER), args=["tr"])
        self.assertEqual(replies, ["settings_owner_only"])
        app.db.set_setting.assert_not_called()

    def test_reading_commands_allowed_for_group_members(self):
        # a non-owner member of the group may read the tariff but not change it
        replies, app = self.run_handler(tg.cmd_tariff, update(chat_id=GROUP, user_id=STRANGER), args=[])
        self.assertEqual(replies, ["tariff_text"])
        app.db.set_setting.assert_not_called()

    def test_bot_leaves_foreign_chats(self):
        app = FakeApp()
        left: list[int] = []

        class Bot:
            async def leave_chat(self, chat_id):
                left.append(chat_id)

        cm = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=-1005555, title="Other group", type="supergroup"),
            new_chat_member=types.SimpleNamespace(status="member"),
        )
        upd = types.SimpleNamespace(my_chat_member=cm)
        asyncio.run(tg._membership(app)(upd, types.SimpleNamespace(bot=Bot())))
        self.assertEqual(left, [-1005555])

    def test_bot_stays_in_its_own_group(self):
        app = FakeApp()
        left: list[int] = []

        class Bot:
            async def leave_chat(self, chat_id):
                left.append(chat_id)

        cm = types.SimpleNamespace(chat=types.SimpleNamespace(id=GROUP, title="Mine", type="supergroup"), new_chat_member=types.SimpleNamespace(status="member"))
        asyncio.run(tg._membership(app)(types.SimpleNamespace(my_chat_member=cm), types.SimpleNamespace(bot=Bot())))
        self.assertEqual(left, [])


if __name__ == "__main__":
    unittest.main()
