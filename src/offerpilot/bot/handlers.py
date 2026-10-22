import logging

from sqlalchemy.orm.session import Session
from telegram import Update
from telegram.ext import ContextTypes

from offerpilot.bot.cards import format_offer_message
from offerpilot.db.models import Customer
from offerpilot.db.session import SessionLocal
from offerpilot.rules.engine import load_catalogue, load_limits, pick_offer

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
        offer = pick_offer(customer, catalogue, limits)
        logger.info("chat_id=%s customer_id=%s offer=%s", chat_id, customer.id, offer.type)

        await update.message.reply_text(format_offer_message(customer, offer))
    finally:
        session.close()
