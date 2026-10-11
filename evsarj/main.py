"""Entry point: `python -m evsarj.main` (Linux, Raspberry Pi, Windows)."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from . import __version__, config
from .app import App
from .db import DB


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)
    # keep library debug output (which could include keys/tokens) out of the logs
    for name in ("tinytuya", "httpx", "httpcore", "telegram"):
        logging.getLogger(name).setLevel(logging.WARNING)


async def amain() -> None:
    setup_logging()
    log = logging.getLogger("evsarj")
    settings, secrets = config.load()
    db = DB(config.BASE_DIR / settings.db_path)
    settings.apply_overrides(db.all_settings())
    app = App(settings, secrets, db)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, app.stop)
        except (NotImplementedError, RuntimeError):
            pass  # Windows: handled through KeyboardInterrupt below
    log.info("ev-charger-bot %s starting (home=%s, device %s…, protocol %s)", __version__, config.BASE_DIR, secrets.tuya_device_id[:6], secrets.tuya_version)
    try:
        await app.run()
    finally:
        db.close()


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
