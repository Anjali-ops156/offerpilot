import logging
from datetime import datetime, timedelta

from sqlalchemy.orm.session import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from offerpilot.agent.agent import run_agent_for_customer
from offerpilot.agent.audit_log import latest_for_customer
from offerpilot.bot.cards import consent_keyboard, format_offer_message, offer_keyboard
from offerpilot.bot.i18n import SUPPORTED_LANGUAGES, t
from offerpilot.db.models import Customer, Event, Feedback
from offerpilot.db.session import SessionLocal
from offerpilot.features.feature_store import compute_features_for_customer
from offerpilot.features.uplift_model import load_models_cached, predict_uplift_for_one
from offerpilot.rules.engine import can_send_now, load_catalogue, load_limits

logger = logging.getLogger(__name__)

DEFAULT_ORDER_VALUE_INR = 1000.0
RATE_LIMIT_SECONDS = 2
SIMULATE_SCENARIOS = {"abandon_cart", "go_inactive", "points_expiring"}
FREQUENCY_CHOICES = {"1": 1, "2": 2, "max": None}  # None = clear override, use the platform default

_last_message_at: dict[int, datetime] = {}  # chat_id -> last handled time (simple in-memory rate limit)


def _is_rate_limited(chat_id: int) -> bool:
    now = datetime.now()
    last = _last_message_at.get(chat_id)
    _last_message_at[chat_id] = now
    return last is not None and (now - last) < timedelta(seconds=RATE_LIMIT_SECONDS)


def _lang(customer: Customer) -> str:
    return customer.language if customer.language in SUPPORTED_LANGUAGES else "en"


def get_or_assign_customer(session: Session, chat_id: int) -> Customer | None:
    """Binds this Telegram chat to a synthetic customer profile, reusing the
    binding on repeat calls so the demo stays consistent per classmate."""
    customer = session.query(Customer).filter_by(telegram_chat_id=chat_id).first()
    if customer:
        return customer

    customer = session.query(Customer).filter_by(telegram_chat_id=None).first()
    if customer:
        customer.telegram_chat_id = chat_id
        session.commit()
    return customer


def _clone_customer(customer: Customer, **overrides) -> Customer:
    """A transient (not session-attached) copy with some fields overridden —
    used by /simulate so a preview never writes to the real customer row."""
    fields = {
        "id": customer.id, "name": customer.name, "city": customer.city,
        "city_tier": customer.city_tier, "age_band": customer.age_band, "gender": customer.gender,
        "language": customer.language, "device": customer.device, "signup_channel": customer.signup_channel,
        "signup_date": customer.signup_date, "loyalty_tier": customer.loyalty_tier,
        "reward_points_balance": customer.reward_points_balance, "consent_opt_in": customer.consent_opt_in,
        "days_since_last_purchase": customer.days_since_last_purchase, "total_spend": customer.total_spend,
        "telegram_chat_id": None,
    }
    fields.update(overrides)
    return Customer(**fields)


async def _run_decision(update: Update, customer: Customer, session: Session, customer_message: str | None = None) -> None:
    """Shared by /start and negotiation replies: decide, send, attach the card."""
    catalogue = load_catalogue()
    limits = load_limits()
    now = datetime.now()
    features = compute_features_for_customer(customer.id, now, session)

    # Cheap pre-check before spending an API call. False: this is a PULL
    # (the classmate is here, talking to the bot right now) — quiet hours
    # is for proactive pushes, not for replying to someone already present.
    ok, reason = can_send_now(
        session, customer.id, limits, limits.max_offer_value_inr, now,
        respect_quiet_hours=False, max_offers_per_week=customer.preferred_max_offers_per_week,
    )
    if not ok:
        logger.info("customer_id=%s blocked: %s", customer.id, reason)
        offer = catalogue.get("no_offer")
        message = format_offer_message(customer, offer)
    else:
        models = load_models_cached()
        uplift = predict_uplift_for_one(customer, features, *models) if models else None
        result = run_agent_for_customer(
            customer, features, catalogue, limits, session, now, uplift,
            respect_quiet_hours=False, customer_message=customer_message,
        )
        offer, message = result["offer"], result["message"]
        logger.info("customer_id=%s offer=%s used_ai=%s", customer.id, offer.type, result["used_ai"])

    await update.effective_message.reply_text(message, reply_markup=offer_keyboard(customer, offer))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if _is_rate_limited(chat_id):
        await update.message.reply_text(t("rate_limited", "en"))
        return

    session = SessionLocal()
    try:
        customer = get_or_assign_customer(session, chat_id)
        if customer is None:
            await update.message.reply_text(
                "Demo is out of synthetic customer profiles — ask the organiser to "
                "regenerate data with a higher --n."
            )
            return

        if not customer.onboarded:
            await update.message.reply_text(
                t("consent_intro", _lang(customer), name=customer.name.split()[0]),
                reply_markup=consent_keyboard(customer),
            )
            return

        if not customer.consent_opt_in:
            # Previously /stop'd — a fresh /start is how they opt back in.
            customer.consent_opt_in = True
            session.commit()

        await _run_decision(update, customer, session)
    finally:
        session.close()


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    if _is_rate_limited(chat_id):
        await query.message.reply_text(t("rate_limited", "en"))
        return

    session = SessionLocal()
    try:
        customer = get_or_assign_customer(session, chat_id)
        if customer is None:
            return
        lang = _lang(customer)
        data = query.data

        if data == "consent_accept":
            customer.onboarded = True
            customer.consent_opt_in = True
            session.commit()
            await _run_decision(update, customer, session)
            return

        if data == "consent_decline":
            customer.onboarded = True
            customer.consent_opt_in = False
            session.commit()
            await query.message.reply_text(t("consent_declined", lang))
            return

        if data == "claim":
            await query.message.reply_text(t("claimed_response", lang))
            return
        if data == "view_cart":
            await query.message.reply_text(t("view_cart_response", lang))
            return
        if data == "not_interested":
            session.add(Feedback(customer_id=customer.id, created_at=datetime.now(), text="[button] not_interested"))
            session.commit()
            await query.message.reply_text(t("not_interested_response", lang))
            return
        if data == "why":
            await _reply_why(query.message.reply_text, customer, session)
            return
        if data.startswith("lang_"):
            await _set_language(query.message.reply_text, customer, session, data.removeprefix("lang_"))
            return
        if data.startswith("freq_"):
            await _set_frequency(query.message.reply_text, customer, session, data.removeprefix("freq_"))
            return
    finally:
        session.close()


async def _reply_why(reply, customer: Customer, session: Session) -> None:
    lang = _lang(customer)
    entry = latest_for_customer(session, customer.id)
    if entry is None:
        await reply(t("why_no_recent_decision", lang))
        return
    reasoning = entry.agent_reasoning_summary or t("why_fallback_reasoning", lang)
    await reply(f"{t('why_intro', lang)}\n\n{reasoning}")


async def why_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if _is_rate_limited(chat_id):
        await update.message.reply_text(t("rate_limited", "en"))
        return
    session = SessionLocal()
    try:
        customer = get_or_assign_customer(session, chat_id)
        if customer is None:
            return
        await _reply_why(update.message.reply_text, customer, session)
    finally:
        session.close()


def _apply_simulation(
    customer: Customer, features: dict, scenario: str, session: Session, now: datetime, limits,
) -> tuple[Customer, dict, str]:
    """Returns (customer_for_preview, features_for_preview, intro_i18n_key).
    Never mutates the real customer row or counts against real quota —
    callers must run the agent with enforce_cadence=False."""
    if scenario == "abandon_cart":
        category = features.get("category_affinity") or "Fashion"
        amount = features.get("avg_order_value") or DEFAULT_ORDER_VALUE_INR
        session.add(Event(customer_id=customer.id, event_type="add_to_cart", timestamp=now, category=category, amount=amount))
        session.add(Event(customer_id=customer.id, event_type="cart_abandon", timestamp=now, category=category, amount=amount))
        session.commit()
        fresh_features = compute_features_for_customer(customer.id, now, session)
        return customer, fresh_features, "simulate_abandon_cart_intro"

    if scenario == "go_inactive":
        inactive_days = limits.win_back_days_threshold + 1
        preview_customer = _clone_customer(customer, days_since_last_purchase=inactive_days)
        preview_features = dict(features)
        preview_features["recency_days"] = inactive_days
        return preview_customer, preview_features, "simulate_go_inactive_intro"

    # points_expiring
    bumped_points = max(customer.reward_points_balance, limits.gold_points_bonus_threshold)
    preview_customer = _clone_customer(customer, reward_points_balance=bumped_points)
    return preview_customer, features, "simulate_points_expiring_intro"


async def simulate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if _is_rate_limited(chat_id):
        await update.message.reply_text(t("rate_limited", "en"))
        return

    session = SessionLocal()
    try:
        customer = get_or_assign_customer(session, chat_id)
        if customer is None or not customer.onboarded:
            await update.message.reply_text("Send /start first.")
            return
        lang = _lang(customer)
        scenario = context.args[0] if context.args else None
        if scenario not in SIMULATE_SCENARIOS:
            await update.message.reply_text(t("simulate_help", lang))
            return

        catalogue = load_catalogue()
        limits = load_limits()
        now = datetime.now()
        features = compute_features_for_customer(customer.id, now, session)
        preview_customer, preview_features, intro_key = _apply_simulation(customer, features, scenario, session, now, limits)

        models = load_models_cached()
        uplift = predict_uplift_for_one(preview_customer, preview_features, *models) if models else None
        result = run_agent_for_customer(
            preview_customer, preview_features, catalogue, limits, session, now, uplift,
            respect_quiet_hours=False, enforce_cadence=False,
        )
        await update.message.reply_text(f"{t(intro_key, lang)}\n\n{result['message']}")
    finally:
        session.close()


async def preferences_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if _is_rate_limited(chat_id):
        await update.message.reply_text(t("rate_limited", "en"))
        return
    session = SessionLocal()
    try:
        customer = get_or_assign_customer(session, chat_id)
        if customer is None:
            return
        lang = _lang(customer)
        limits = load_limits()
        frequency = customer.preferred_max_offers_per_week or limits.max_offers_per_week

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("English", callback_data="lang_en"),
                InlineKeyboardButton("Hindi", callback_data="lang_hi"),
                InlineKeyboardButton("Punjabi", callback_data="lang_pa"),
            ],
            [
                InlineKeyboardButton("1 / week", callback_data="freq_1"),
                InlineKeyboardButton("2 / week", callback_data="freq_2"),
                InlineKeyboardButton("Default", callback_data="freq_max"),
            ],
        ])
        await update.message.reply_text(
            t("preferences_menu", lang, language=lang, frequency=frequency), reply_markup=keyboard,
        )
    finally:
        session.close()


async def _set_language(reply, customer: Customer, session: Session, language: str) -> None:
    if language not in SUPPORTED_LANGUAGES:
        return
    customer.language = language
    session.commit()
    await reply(t("preferences_language_updated", language, language=language))


async def _set_frequency(reply, customer: Customer, session: Session, choice: str) -> None:
    if choice not in FREQUENCY_CHOICES:
        return
    customer.preferred_max_offers_per_week = FREQUENCY_CHOICES[choice]
    session.commit()
    lang = _lang(customer)
    limits = load_limits()
    shown = customer.preferred_max_offers_per_week or limits.max_offers_per_week
    await reply(t("preferences_frequency_updated", lang, frequency=shown))


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    session = SessionLocal()
    try:
        customer = get_or_assign_customer(session, chat_id)
        if customer is None:
            return
        customer.consent_opt_in = False
        session.commit()
        await update.message.reply_text(t("stop_confirm", _lang(customer)))
    finally:
        session.close()


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if _is_rate_limited(chat_id):
        await update.message.reply_text(t("rate_limited", "en"))
        return
    session = SessionLocal()
    try:
        customer = get_or_assign_customer(session, chat_id)
        if customer is None:
            return
        lang = _lang(customer)
        text = " ".join(context.args) if context.args else ""
        if not text.strip():
            await update.message.reply_text(t("feedback_prompt", lang))
            return
        session.add(Feedback(customer_id=customer.id, created_at=datetime.now(), text=text.strip()))
        session.commit()
        await update.message.reply_text(t("feedback_thanks", lang))
    finally:
        session.close()


async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Negotiation mode: a plain-text reply to an existing offer. The text
    is passed to the agent as UNTRUSTED DATA (see agent.SYSTEM_PROMPT) —
    never as instructions, whatever it claims to say."""
    chat_id = update.effective_chat.id
    if _is_rate_limited(chat_id):
        await update.message.reply_text(t("rate_limited", "en"))
        return

    session = SessionLocal()
    try:
        customer = get_or_assign_customer(session, chat_id)
        if customer is None or not customer.onboarded:
            return
        lang = _lang(customer)

        entry = latest_for_customer(session, customer.id)
        if entry is None or entry.final_offer_type == "no_offer":
            await update.message.reply_text(t("negotiation_blocked", lang))
            return

        await _run_decision(update, customer, session, customer_message=update.message.text)
    finally:
        session.close()


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error while processing update: %s", update, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(t("generic_error", "en"))
        except Exception:
            logger.exception("Failed to notify user of error")
