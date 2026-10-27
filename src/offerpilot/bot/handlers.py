import logging
from datetime import datetime

from sqlalchemy.orm.session import Session
from telegram import Update
from telegram.ext import ContextTypes

from offerpilot.agent.agent import run_agent_for_customer
from offerpilot.bot.cards import format_offer_message
from offerpilot.db.models import Customer
from offerpilot.db.session import SessionLocal
from offerpilot.features.feature_store import compute_features_for_customer
from offerpilot.features.uplift_model import load_models_cached, predict_uplift_for_one
from offerpilot.rules.engine import can_send_now, load_catalogue, load_limits

logger = logging.getLogger(__name__)


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


def _estimate_uplift(customer: Customer, features: dict) -> float | None:
    models = load_models_cached()
    if models is None:
        return None
    model_t, model_c = models
    try:
        return predict_uplift_for_one(customer, features, model_t, model_c)
    except Exception:
        logger.exception("uplift prediction failed for customer_id=%s", customer.id)
        return None


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

        # Cheap pre-check with a worst-case cost, BEFORE spending an API call on
        # the agent: /start is a pull (the classmate opened the bot themselves),
        # so quiet hours doesn't apply — frequency/cooldown/budget still do.
        ok, reason = can_send_now(session, customer.id, limits, limits.max_offer_value_inr, now, respect_quiet_hours=False)
        if not ok:
            logger.info("chat_id=%s customer_id=%s pre-check blocked: %s", chat_id, customer.id, reason)
            offer = catalogue.get("no_offer")
            message = format_offer_message(customer, offer)
        else:
            uplift_score = _estimate_uplift(customer, features)
            result = run_agent_for_customer(customer, features, catalogue, limits, session, now, uplift_score)
            offer, message = result["offer"], result["message"]
            logger.info(
                "chat_id=%s customer_id=%s offer=%s used_ai=%s",
                chat_id, customer.id, offer.type, result["used_ai"],
            )

        await update.message.reply_text(message)
    finally:
        session.close()
