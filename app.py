"""Vercel entrypoint: the same bot as bot/main.py, but driven by Telegram
webhooks (one HTTP POST per update) instead of long-polling — long-polling
needs an always-on process, which a serverless function cannot be.

Local development still uses `python -m offerpilot.bot.main` (polling).
This file is ONLY the deployed path. Point Telegram's webhook at
https://<your-deployment>/api/webhook after deploying — see
scripts/set_webhook.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from fastapi import FastAPI, Request  # noqa: E402
from telegram import Update  # noqa: E402
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters  # noqa: E402

from offerpilot.bot.handlers import (  # noqa: E402
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
from offerpilot.config import TELEGRAM_BOT_TOKEN  # noqa: E402
from offerpilot.db.session import init_db  # noqa: E402

app = FastAPI()

_bot_app: Application | None = None


def _build_application() -> Application:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("why", why_command))
    application.add_handler(CommandHandler("simulate", simulate_command))
    application.add_handler(CommandHandler("preferences", preferences_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("feedback", feedback_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))
    application.add_error_handler(on_error)
    return application


async def _get_bot_app() -> Application:
    """Built once per warm serverless instance (Vercel's Fluid compute can
    reuse one instance across requests), rebuilt on a cold start."""
    global _bot_app
    if _bot_app is None:
        init_db()
        application = _build_application()
        await application.initialize()
        _bot_app = application
    return _bot_app


@app.post("/api/webhook")
async def telegram_webhook(request: Request) -> dict:
    data = await request.json()
    application = await _get_bot_app()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}


@app.get("/")
def health() -> dict:
    return {"status": "OfferPilot bot is running", "docs": "https://github.com/Anjali-ops156/offerpilot"}
