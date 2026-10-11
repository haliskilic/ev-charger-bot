"""Application core: charger thread ↔ state machine ↔ Telegram queue ↔ scheduler."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

from .config import Secrets, Settings
from .db import DB
from .monitor import Monitor, Session
from .reports import Reports
from .summaries import day_bounds, month_bounds, period_stats, prev_month, week_bounds
from .tuya_client import TuyaClient

log = logging.getLogger("evsarj.app")


class App:
    """Sink for the Monitor; also runs the sender, tick and scheduler tasks."""

    def __init__(self, settings: Settings, secrets: Secrets, db: DB):
        self.s = settings
        self.sec = secrets
        self.db = db
        self.R = Reports(settings)
        self.monitor = Monitor(settings, db, self, self.R)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queue: asyncio.Queue = asyncio.Queue()
        self.bot: Bot | None = None
        self.tuya = TuyaClient(secrets, settings, self._post_from_thread, ip_override=db.get_meta("device_ip"))
        self._last_live = 0.0
        self._restart_sent = False
        self._stopping = asyncio.Event()

    # ------------------------------------------------------------------ thread bridge
    def _post_from_thread(self, msg: dict) -> None:
        if self.loop:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, msg)

    # ------------------------------------------------------------------ Sink
    def quiet_now(self, ts: float | None = None) -> bool:
        d = datetime.fromtimestamp(ts or time.time(), self.s.tz)
        cur = d.hour * 60 + d.minute
        h1, m1 = map(int, self.s.quiet_start.split(":"))
        h2, m2 = map(int, self.s.quiet_end.split(":"))
        a, b = h1 * 60 + m1, h2 * 60 + m2
        return (a <= cur < b) if a <= b else (cur >= a or cur < b)

    def event(self, ts: float, etype: str, text: str, details: dict | None, session_id: int | None) -> None:
        self.db.insert_event(ts, session_id, etype, text, details)
        self.db.enqueue("msg", text, ts, silent=self.quiet_now(ts))
        log.info("event %s: %s", etype, text.splitlines()[0])

    def live_create(self, session: Session) -> None:
        text = self.R.live_status(session, self.monitor.st, time.time())
        self.db.enqueue("live_create", text, time.time(), silent=True, extra={"session_id": session.id})
        self._last_live = time.time()

    def live_update(self, session: Session, final: bool = False) -> None:
        if not session.live_message_id:
            return
        text = self.R.live_status(session, self.monitor.st, time.time(), final=final)
        row_id = self.db.enqueue("edit", text, time.time(), silent=True, message_id=session.live_message_id)
        self.db.drop_pending_edits_for(session.live_message_id, row_id)
        self._last_live = time.time()

    def interim(self, session: Session) -> None:
        text = self.R.interim(session, self.monitor.st, time.time())
        self.db.enqueue("msg", text, time.time(), silent=self.quiet_now())

    def session_closed(self, session: Session, text: str) -> None:
        if session.live_message_id:
            self.live_update(session, final=True)

    def fast(self, fast: bool) -> None:
        self.tuya.set_fast(fast)

    # ------------------------------------------------------------------ runtime settings
    def reload_settings(self) -> None:
        self.s.apply_overrides(self.db.all_settings())
        self.R.set_language(self.s.language)
        self.R.F.currency = self.s.tariff.currency

    # ------------------------------------------------------------------ tasks
    async def consume_queue(self) -> None:
        while not self._stopping.is_set():
            try:
                msg = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                if msg["kind"] == "dps":
                    self.monitor.on_dps(msg["ts"], msg["dps"], msg.get("snapshot", False))
                    if self.monitor.initialized and not self._restart_sent:
                        self._send_restart_message()
                elif msg["kind"] == "conn":
                    self.monitor.on_conn(msg["ts"], msg["state"], msg.get("info", {}))
            except Exception:
                log.exception("error while handling %s", msg.get("kind"))

    def _send_restart_message(self) -> None:
        self._restart_sent = True
        now = time.time()
        text = self.R.bot_restarted(now, self.monitor.st, self.monitor.sess)
        self.db.insert_event(now, None, "bot_started", text, None)
        self.db.enqueue("msg", text, now, silent=self.quiet_now())

    async def tick(self) -> None:
        start = time.time()
        while not self._stopping.is_set():
            await asyncio.sleep(1.0)
            now = time.time()
            try:
                self.monitor.on_tick(now)
            except Exception:
                log.exception("tick error")
            if not self._restart_sent and now - start > 45:
                self._send_restart_message()  # charger unreachable for 45 s: announce the start anyway

    async def sender(self) -> None:
        assert self.bot is not None
        while not self._stopping.is_set():
            row = self.db.next_outbox()
            if row is None:
                await asyncio.sleep(1.0)
                continue
            try:
                await self._send_row(row)
            except RetryAfter as e:
                log.warning("Telegram rate limit: %s s", e.retry_after)
                await asyncio.sleep(float(e.retry_after) + 1)
            except (NetworkError, TimedOut) as e:
                self.db.outbox_fail(row["id"], str(e), final=False)
                wait = min(60, 5 * (row["attempts"] + 1))
                log.warning("Telegram unreachable (%s), retrying in %d s", e, wait)
                await asyncio.sleep(wait)
            except BadRequest as e:
                msg = str(e).lower()
                if "not modified" in msg:
                    self.db.outbox_done(row["id"], None)
                elif "message to edit not found" in msg or "can't be edited" in msg:
                    self.db.outbox_fail(row["id"], str(e), final=True)
                else:
                    log.error("Telegram BadRequest: %s", e)
                    self.db.outbox_fail(row["id"], str(e), final=True)
            except Forbidden as e:
                log.error("Telegram permission error: %s", e)
                self.db.outbox_fail(row["id"], str(e), final=True)
                await asyncio.sleep(30)
            except Exception as e:
                log.exception("send error")
                self.db.outbox_fail(row["id"], str(e), final=row["attempts"] >= 10)
                await asyncio.sleep(10)

    async def _send_row(self, row) -> None:
        assert self.bot is not None
        kind = row["kind"]
        text = row["text"]
        silent = bool(row["silent"]) or self.quiet_now()
        now = time.time()
        if kind == "msg" and now - row["event_ts"] > 120:
            text = self.R.L("delayed_prefix", when=self.R.F.when(row["event_ts"])) + "\n" + text
        if kind in ("msg", "live_create"):
            m = await self.bot.send_message(
                chat_id=self.sec.tg_chat_id, text=text, message_thread_id=self.sec.tg_thread_id,
                parse_mode=ParseMode.HTML, disable_notification=silent,
            )
            self.db.outbox_done(row["id"], m.message_id)
            if kind == "live_create":
                extra = json.loads(row["extra_json"] or "{}")
                sid = extra.get("session_id")
                if sid:
                    self.db.update_session(sid, live_message_id=m.message_id)
                    if self.monitor.sess and self.monitor.sess.id == sid:
                        self.monitor.sess.live_message_id = m.message_id
        elif kind == "edit":
            await self.bot.edit_message_text(text=text, chat_id=self.sec.tg_chat_id, message_id=row["message_id"], parse_mode=ParseMode.HTML)
            self.db.outbox_done(row["id"], None)
        else:
            self.db.outbox_fail(row["id"], f"unknown kind {kind}", final=True)

    async def scheduler(self) -> None:
        while not self._stopping.is_set():
            await asyncio.sleep(15)
            try:
                self._scheduled_jobs(time.time())
            except Exception:
                log.exception("scheduler error")

    def _scheduled_jobs(self, now: float) -> None:
        d = datetime.fromtimestamp(now, self.s.tz)
        sess = self.monitor.sess
        if sess and sess.seg and sess.live_message_id and now - self._last_live >= self.s.live_status_min * 60:
            self.live_update(sess)
        hhmm = d.strftime("%H:%M")
        today = d.strftime("%Y-%m-%d")
        if hhmm >= self.s.daily_time and self.db.get_meta("last_daily") != today:
            self.db.set_meta("last_daily", today)
            self.send_daily(d)
        if d.weekday() == 0 and hhmm >= self.s.weekly_time and self.db.get_meta("last_weekly") != today:
            self.db.set_meta("last_weekly", today)
            self.send_weekly(d - timedelta(days=1), scheduled=True)
        if d.day == 1 and hhmm >= self.s.monthly_time and self.db.get_meta("last_monthly") != today:
            self.db.set_meta("last_monthly", today)
            self.send_monthly(prev_month(d), scheduled=True)
        if hhmm >= "03:30" and self.db.get_meta("last_cleanup") != today:
            self.db.set_meta("last_cleanup", today)
            counts = self.db.purge(self.s.samples_days, self.s.transitions_months, self.s.events_months)
            log.info("retention cleanup: %s", counts)
            if d.day == 1:
                self.db.vacuum()

    # ------------------------------------------------------------------ periodic summary texts
    def daily_text(self, d: datetime) -> str:
        t0, t1 = day_bounds(d)
        p0, p1 = day_bounds(d - timedelta(days=1))
        stats = period_stats(self.db, self.s, t0, t1)
        prev = period_stats(self.db, self.s, p0, p1)
        return self.R.period_summary(self.R.L("daily_title", date=self.R.F.date_long(d)), stats, prev, self.R.L("vs_yesterday"), self.db.lifetime_kwh(), bool(stats["open_n"]))

    def weekly_text(self, d: datetime, scheduled: bool = False) -> str:
        t0, t1, ds, de = week_bounds(d)
        p0, p1, _, _ = week_bounds(ds - timedelta(days=1))
        stats = period_stats(self.db, self.s, t0, t1)
        prev = period_stats(self.db, self.s, p0, p1)
        title = self.R.L("weekly_title", range=self.R.F.range_days(ds, de)) + ("" if scheduled else self.R.L("so_far"))
        return self.R.period_summary(title, stats, prev, self.R.L("vs_prev_week"), self.db.lifetime_kwh())

    def monthly_text(self, d: datetime, scheduled: bool = False) -> str:
        t0, t1, ds = month_bounds(d)
        p0, p1, ps = month_bounds(prev_month(d))
        stats = period_stats(self.db, self.s, t0, t1)
        prev = period_stats(self.db, self.s, p0, p1)
        title = self.R.L("monthly_title", month=self.R.F.month_name(ds)) + ("" if scheduled else self.R.L("so_far"))
        return self.R.period_summary(title, stats, prev, self.R.L("vs_month", month=self.R.F.month_only(ps)), self.db.lifetime_kwh())

    def send_daily(self, d: datetime) -> None:
        t0, t1 = day_bounds(d)
        stats = period_stats(self.db, self.s, t0, t1)
        if stats["n"] == 0:
            if self.s.no_charge_day_message:
                self.db.enqueue("msg", self.R.no_charge_day(d, self.monitor.st.online), time.time(), silent=self.quiet_now())
            return
        self.db.enqueue("msg", self.daily_text(d), time.time(), silent=self.quiet_now())

    def send_weekly(self, d: datetime, scheduled: bool = False) -> None:
        self.db.enqueue("msg", self.weekly_text(d, scheduled), time.time(), silent=self.quiet_now())

    def send_monthly(self, d: datetime, scheduled: bool = False) -> None:
        self.db.enqueue("msg", self.monthly_text(d, scheduled), time.time(), silent=self.quiet_now())

    # ------------------------------------------------------------------ lifecycle
    async def run(self) -> None:
        from .telegram_bot import build_application

        self.loop = asyncio.get_running_loop()
        application = build_application(self)
        self.bot = application.bot
        await application.initialize()
        await application.start()
        await application.updater.start_polling(allowed_updates=["message", "my_chat_member"], drop_pending_updates=True)
        self.tuya.start()
        tasks = [
            asyncio.create_task(self.consume_queue(), name="queue"),
            asyncio.create_task(self.tick(), name="tick"),
            asyncio.create_task(self.sender(), name="sender"),
            asyncio.create_task(self.scheduler(), name="scheduler"),
        ]
        log.info("bot running (language=%s)", self.s.language)
        try:
            await self._stopping.wait()
        finally:
            log.info("stopping")
            self.tuya.stop()
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                self.monitor._persist_session()
            except Exception:
                pass
            await application.updater.stop()
            await application.stop()
            await application.shutdown()

    def stop(self) -> None:
        self._stopping.set()
