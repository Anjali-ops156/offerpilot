"""Proactive push: for every customer who has already connected (sent
/start at least once — Telegram requires that one-time contact before a bot
is allowed to message someone first), runs the SAME agent decision
pipeline used for /start, but unprompted. Unlike /start, quiet hours IS
enforced here — this is a genuine push, not a reply to the customer
opening the chat.

Safe to run on any schedule (cron, Windows Task Scheduler, a loop) — each
run only pushes to customers who are currently eligible for something AND
not already capped by frequency/cooldown/budget, so running it hourly
doesn't spam anyone twice.

Usage: python -m offerpilot.agent.proactive_push
"""
import asyncio
import logging
from datetime import datetime

from telegram import Bot

from offerpilot.agent.agent import run_agent_for_customer
from offerpilot.config import TELEGRAM_BOT_TOKEN
from offerpilot.db.models import Customer
from offerpilot.db.session import SessionLocal
from offerpilot.features.feature_store import compute_features_for_customer
from offerpilot.features.uplift_model import load_models_cached, predict_uplift_for_one
from offerpilot.rules.engine import can_send_now, load_catalogue, load_limits

logger = logging.getLogger(__name__)


async def push_to_eligible_customers() -> dict:
    session = SessionLocal()
    sent, skipped = 0, 0
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        catalogue = load_catalogue()
        limits = load_limits()
        now = datetime.now()
        models = load_models_cached()

        customers = session.query(Customer).filter(Customer.telegram_chat_id.isnot(None)).all()
        for customer in customers:
            features = compute_features_for_customer(customer.id, now, session)

            # Cheap pre-check with a worst-case cost before spending an API
            # call. True here: this IS a proactive push, quiet hours applies.
            ok, reason = can_send_now(
                session, customer.id, limits, limits.max_offer_value_inr, now,
                respect_quiet_hours=True, max_offers_per_week=customer.preferred_max_offers_per_week,
            )
            if not ok:
                logger.info("customer_id=%s skipped: %s", customer.id, reason)
                skipped += 1
                continue

            uplift_score = None
            if models is not None:
                try:
                    uplift_score = predict_uplift_for_one(customer, features, *models)
                except Exception:
                    logger.exception("uplift prediction failed for customer_id=%s", customer.id)

            result = run_agent_for_customer(
                customer, features, catalogue, limits, session, now, uplift_score, respect_quiet_hours=True,
            )
            if result["offer"].type == "no_offer":
                logger.info("customer_id=%s: agent decided no_offer", customer.id)
                skipped += 1
                continue

            await bot.send_message(chat_id=customer.telegram_chat_id, text=result["message"])
            logger.info(
                "pushed %s to customer_id=%s chat_id=%s (used_ai=%s)",
                result["offer"].type, customer.id, customer.telegram_chat_id, result["used_ai"],
            )
            sent += 1
    finally:
        session.close()
    return {"sent": sent, "skipped": skipped}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    summary = asyncio.run(push_to_eligible_customers())
    print(f"Proactive push complete: {summary['sent']} sent, {summary['skipped']} skipped.")
