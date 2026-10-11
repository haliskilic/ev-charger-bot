"""Telegram commands and access control.

Security model:
  * Only updates from the configured group chat are processed; everything else (private chats, other groups,
    channels) is silently ignored — the bot never answers strangers.
  * If the bot is added to any other chat it leaves immediately.
  * Commands that change settings (/settings, /tariff, /language) are accepted only from the owner's user id.
  * The bot is read-only towards the charger: no command can start/stop charging or change its settings.
"""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING

from telegram import InputFile, Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import Application, ChatMemberHandler, CommandHandler, ContextTypes, filters

from .i18n import LANGUAGES

if TYPE_CHECKING:
    from .app import App

log = logging.getLogger("evsarj.tg")

# English command → Turkish alias. Both work regardless of the active language.
COMMANDS = {
    "help": "yardim", "status": "durum", "session": "oturum", "today": "bugun", "week": "hafta", "month": "ay",
    "history": "gecmis", "tariff": "tarife", "settings": "ayar", "raw": "ham", "export": "disaaktar", "language": "dil",
}


def build_application(app: "App") -> Application:
    application = Application.builder().token(app.sec.tg_token).build()
    only_group = filters.Chat(chat_id=app.sec.tg_chat_id)
    handlers = {
        "help": cmd_help, "start": cmd_help, "status": cmd_status, "session": cmd_session, "today": cmd_today,
        "week": cmd_week, "month": cmd_month, "history": cmd_history, "tariff": cmd_tariff, "settings": cmd_settings,
        "raw": cmd_raw, "export": cmd_export, "language": cmd_language,
    }
    for name, fn in handlers.items():
        names = [name] + ([COMMANDS[name]] if name in COMMANDS else [])
        application.add_handler(CommandHandler(names, _wrap(app, fn), filters=only_group))
    application.add_handler(ChatMemberHandler(_membership(app), ChatMemberHandler.MY_CHAT_MEMBER))
    return application


def is_allowed_chat(app: "App", chat_id: int | None) -> bool:
    return chat_id is not None and chat_id == app.sec.tg_chat_id


def is_owner(app: "App", user_id: int | None) -> bool:
    return user_id is not None and user_id == app.sec.tg_owner_id


def _wrap(app: "App", fn):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        chat = update.effective_chat
        if msg is None or chat is None or not is_allowed_chat(app, chat.id):
            return  # anything outside the configured group is ignored
        try:
            text = await fn(app, update, context)
        except Exception:
            log.exception("command failed: %s", msg.text)
            text = app.R.L("cmd_error")
        if text:
            await reply(app, update, text)

    return handler


def _membership(app: "App"):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        cm = update.my_chat_member
        if cm is None or is_allowed_chat(app, cm.chat.id):
            return
        if cm.new_chat_member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.RESTRICTED):
            log.warning("added to a foreign chat %s (%s); leaving", cm.chat.id, cm.chat.title or cm.chat.type)
            try:
                await context.bot.leave_chat(cm.chat.id)
            except Exception:
                log.exception("could not leave chat %s", cm.chat.id)

    return handler


async def reply(app: "App", update: Update, text: str, document: tuple[str, bytes] | None = None) -> None:
    msg = update.effective_message
    thread = msg.message_thread_id if msg and msg.is_topic_message else None
    bot = app.bot
    assert bot is not None
    try:
        if document:
            name, data = document
            await bot.send_document(
                chat_id=app.sec.tg_chat_id, document=InputFile(io.BytesIO(data), filename=name),
                caption=text, message_thread_id=thread, parse_mode=ParseMode.HTML,
            )
        else:
            await bot.send_message(chat_id=app.sec.tg_chat_id, text=text, message_thread_id=thread, parse_mode=ParseMode.HTML)
    except Exception:
        log.exception("reply failed")


def _owner(app: "App", update: Update) -> bool:
    return is_owner(app, update.effective_user.id if update.effective_user else None)


async def cmd_help(app: "App", update: Update, context) -> str:
    return app.R.help_cmd()


async def cmd_status(app: "App", update: Update, context) -> str:
    now = time.time()
    return app.R.status_cmd(app.monitor.status_dict(now), app.db.last_closed_session(), now, app.db.outbox_pending_count())


async def cmd_session(app: "App", update: Update, context) -> str:
    return app.R.session_cmd(app.monitor.sess, app.monitor.st, app.db.last_closed_session(), time.time())


async def cmd_today(app: "App", update: Update, context) -> str:
    return app.daily_text(datetime.now(app.s.tz))


async def cmd_week(app: "App", update: Update, context) -> str:
    return app.weekly_text(datetime.now(app.s.tz))


async def cmd_month(app: "App", update: Update, context) -> str:
    return app.monthly_text(datetime.now(app.s.tz))


async def cmd_history(app: "App", update: Update, context) -> str:
    n = 10
    if context.args:
        try:
            n = max(1, min(50, int(context.args[0])))
        except ValueError:
            pass
    return app.R.history_cmd(app.db.recent_sessions(n))


async def cmd_tariff(app: "App", update: Update, context) -> str:
    args = [a.lower() for a in (context.args or [])]
    if not args:
        return app.R.tariff_cmd()
    if not _owner(app, update):
        return app.R.L("tariff_owner_only")
    try:
        if args[0] in ("single", "tek") and len(args) == 2:
            app.db.set_setting("tariff_type", "single")
            app.db.set_setting("tariff_single", str(float(args[1].replace(",", "."))))
        elif args[0] in ("tou", "uc", "üç") and len(args) == 4:
            day, peak, night = (float(x.replace(",", ".")) for x in args[1:4])
            for k, v in (("tariff_type", "tou"), ("tariff_day", str(day)), ("tariff_peak", str(peak)), ("tariff_night", str(night))):
                app.db.set_setting(k, v)
        else:
            return app.R.L("tariff_usage")
    except ValueError:
        return app.R.L("tariff_number")
    app.reload_settings()
    return app.R.L("tariff_updated") + "\n" + app.R.tariff_cmd()


async def cmd_settings(app: "App", update: Update, context) -> str:
    args = [a.lower() for a in (context.args or [])]
    if not args:
        return app.R.settings_cmd()
    if not _owner(app, update):
        return app.R.L("settings_owner_only")
    if len(args) != 2:
        return app.R.L("settings_usage")
    key, value = args
    try:
        if key in ("live", "canli"):
            app.db.set_setting("live_status_min", str(max(1, int(value))))
        elif key in ("interim", "ara"):
            app.db.set_setting("interim_report_min", str(max(5, int(value))))
        elif key in ("quiet", "sessiz"):
            a, _, b = value.partition("-")
            h1, h2 = int(a), int(b)
            if not (0 <= h1 <= 23 and 0 <= h2 <= 23):
                raise ValueError
            app.db.set_setting("quiet_hours", f"{h1:02d}:00-{h2:02d}:00")
        elif key in ("nochargeday", "bosgun"):
            app.db.set_setting("no_charge_day_message", "1" if value in ("on", "acik", "açık", "1", "true") else "0")
        else:
            return app.R.L("settings_unknown")
    except ValueError:
        return app.R.L("settings_invalid")
    app.reload_settings()
    return app.R.L("settings_updated") + "\n" + app.R.settings_cmd()


async def cmd_language(app: "App", update: Update, context) -> str:
    args = [a.lower() for a in (context.args or [])]
    if not args or args[0] not in LANGUAGES:
        return app.R.L("language_usage")
    if not _owner(app, update):
        return app.R.L("settings_owner_only")
    app.db.set_setting("language", args[0])
    app.reload_settings()
    return app.R.L("language_set", name=app.R.L("lang_name"))


async def cmd_raw(app: "App", update: Update, context) -> str:
    info = app.monitor.status_dict(time.time())
    return app.R.raw_cmd(info["raw"], info["raw_ts"], time.time())


async def cmd_export(app: "App", update: Update, context) -> str | None:
    args = [a.lower() for a in (context.args or [])]
    tz = app.s.tz
    L = app.R.L
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    today = datetime.now(tz).strftime("%Y-%m-%d")
    if args and args[0] in ("raw", "ham"):
        days = 7
        if len(args) > 1:
            try:
                days = max(1, min(90, int(args[1])))
            except ValueError:
                pass
        t1 = time.time()
        t0 = t1 - days * 86400
        w.writerow(L("csv_samples").split(";"))
        n = 0
        for r in app.db.samples_between(t0, t1):
            w.writerow([
                datetime.fromtimestamp(r["ts"], tz).strftime("%Y-%m-%d %H:%M:%S"), r["session_id"], r["work_state"], r["switch"], r["cur_set"],
                r["work_mode"], r["fault"], r["power_kw"], r["va"], r["ia"], r["pa"], r["vb"], r["ib"], r["pb"], r["vc"], r["ic"], r["pc"], r["timer_raw"],
            ])
            n += 1
        name = L("csv_samples_name", days=days, date=today)
        await reply(app, update, L("export_samples", name=name, n=n), (name, buf.getvalue().encode("utf-8-sig")))
        return None
    w.writerow(L("csv_sessions").split(";"))
    rows = app.db.all_sessions()

    def t(ts):
        return datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M") if ts else ""

    for r in rows:
        w.writerow([
            r["id"], r["source"], t(r["plug_ts"]), t(r["charge_start_ts"]), t(r["charge_end_ts"]), t(r["unplug_ts"]),
            round((r["plugged_s"] or 0) / 60), round((r["charge_s"] or 0) / 60), r["energy_kwh"], r["energy_calc_kwh"], r["energy_device_kwh"],
            r["avg_kw"], r["peak_kw"], r["cost"], app.R.end_reason(r["end_reason"], closed=bool(r["closed"])), r["warnings_json"], r["notes_json"],
        ])
    name = L("csv_sessions_name", date=today)
    await reply(app, update, L("export_sessions", name=name, n=len(rows)), (name, buf.getvalue().encode("utf-8-sig")))
    return None
