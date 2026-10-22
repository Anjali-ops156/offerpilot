import logging
from datetime import datetime

from sqlalchemy.orm.session import Session
from telegram import Update
from telegram.ext import ContextTypes

from offerpilot.bot.cards import format_offer_message
from offerpilot.db.models import Customer
from offerpilot.db.session import SessionLocal
from offerpilot.features.feature_store import compute_features_for_customer
from offerpilot.features.next_best_action import offer_cost_inr
from offerpilot.rules.engine import can_send_now, load_catalogue, load_limits, pick_offer, record_sent_offer

logger = logging.getLogger(__name__)

DEFAULT_ORDER_VALUE_INR = 1000.0  # fallback for a customer with no purchase history yet


def get_or_assign_customer(session: Session, chat_id: int) -> Customer | None:
    """Binds this Telegram chat to a synthetic customer profile, reusing the
    binding on repeat /start calls so the demo stays consistent per classmate."""
    customer = session.query(Customer).filter_by(telegram_chat_id=chat_id).first()
    if customer:
        return customer

    customer = session.query(Customer).filter_by(telegram_chat_id=None).first()
    if customer:
        customer.telegram_chat_id = chat_id
        session.commit()
    return customer


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    session = SessionLocal()
    try:
        customer = get_or_assign_customer(session, chat_id)
        if customer is None:
            await update.message.reply_text(
                "Demo is out of synthetic customer profiles — ask the organiser to "
                "regenerate data with a higher --n."
            )
            return

        catalogue = load_catalogue()
        limits = load_limits()
        now = datetime.now()
        features = compute_features_for_customer(customer.id, now, session)

        offer = pick_offer(customer, features, catalogue, limits)
        cost = offer_cost_inr(features.get("avg_order_value") or DEFAULT_ORDER_VALUE_INR, offer, limits)

        # /start is the classmate opening the bot themselves (pull, not a
        # proactive push) — quiet hours shouldn't refuse someone who's
        # already here, but frequency/cooldown/budget guardrails still apply.
        ok, reason = can_send_now(session, customer.id, limits, cost, now, respect_quiet_hours=False)
        if ok:
            if offer.type != "no_offer":
                record_sent_offer(session, customer.id, offer.type, cost, now)
        else:
            logger.info("chat_id=%s customer_id=%s offer blocked: %s", chat_id, customer.id, reason)
            offer = catalogue.get("no_offer")

        logger.info("chat_id=%s customer_id=%s offer=%s", chat_id, customer.id, offer.type)
        await update.message.reply_text(format_offer_message(customer, offer))
    finally:
        session.close()
