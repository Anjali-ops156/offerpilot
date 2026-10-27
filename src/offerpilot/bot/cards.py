from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from offerpilot.bot.i18n import t
from offerpilot.db.models import Customer
from offerpilot.rules.schema import Offer

LABEL_FIELD = {"en": "label_en", "hi": "label_hi", "pa": "label_pa"}


def _lang(customer: Customer) -> str:
    return customer.language if customer.language in LABEL_FIELD else "en"


def format_offer_message(customer: Customer, offer: Offer) -> str:
    lang = _lang(customer)
    greeting = t("greeting", lang, name=customer.name.split()[0])
    if offer.kind == "none":
        body = t("no_offer_text", lang)
    else:
        body = getattr(offer, LABEL_FIELD[lang]).format(pct=int(offer.value))
    return f"{greeting}\n\n{body}"


def offer_keyboard(customer: Customer, offer: Offer) -> InlineKeyboardMarkup | None:
    """Claim / View cart / Not interested / Why this offer? — only for a
    real offer; no_offer gets no buttons (nothing to act on)."""
    if offer.kind == "none":
        return None
    lang = _lang(customer)
    row1 = [
        InlineKeyboardButton(t("claim_button", lang), callback_data="claim"),
        InlineKeyboardButton(t("view_cart_button", lang), callback_data="view_cart"),
    ]
    row2 = [
        InlineKeyboardButton(t("not_interested_button", lang), callback_data="not_interested"),
        InlineKeyboardButton(t("why_button", lang), callback_data="why"),
    ]
    return InlineKeyboardMarkup([row1, row2])


def consent_keyboard(customer: Customer) -> InlineKeyboardMarkup:
    lang = _lang(customer)
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t("consent_accept_button", lang), callback_data="consent_accept"),
        InlineKeyboardButton(t("consent_decline_button", lang), callback_data="consent_decline"),
    ]])
