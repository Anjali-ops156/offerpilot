"""Thin-slice Telegram bot entrypoint: /start -> one rule-picked offer.
Run with: python -m offerpilot.bot.main
"""
import logging

from telegram.ext import Application, CommandHandler

from offerpilot.bot.handlers import start
from offerpilot.config import TELEGRAM_BOT_TOKEN
from offerpilot.db.session import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in."
        )

    init_db()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    logging.getLogger(__name__).info("OfferPilot bot starting (long polling)...")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
