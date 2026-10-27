"""Telegram bot entrypoint — the full Phase 5 bot: consent onboarding, an
AI-decided offer with a rich card, /why, /simulate, /preferences, /stop,
/feedback, and free-text negotiation.
Run with: python -m offerpilot.bot.main
"""
import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from offerpilot.bot.handlers import (
    feedback_command,
    handle_callback,
    handle_free_text,
    on_error,
    preferences_command,
    simulate_command,
    start,
    stop_command,
    why_command,
)
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
    app.add_handler(CommandHandler("why", why_command))
    app.add_handler(CommandHandler("simulate", simulate_command))
    app.add_handler(CommandHandler("preferences", preferences_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))
    app.add_error_handler(on_error)

    logging.getLogger(__name__).info("OfferPilot bot starting (long polling)...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
