from offerpilot.db.models import Customer
from offerpilot.rules.schema import Offer

LABEL_FIELD = {"en": "label_en", "hi": "label_hi", "pa": "label_pa"}

NO_OFFER_TEXT = {
    "en": "Nothing new for you right now — check back soon!",
    "hi": "Abhi aapke liye koi naya offer nahi hai — jald hi dobara dekhein!",
    "pa": "Hun tuhade layi koi nava offer nahi hai — jaldi dubara vekho!",
}

GREETING = {
    "en": "Hi {name}! This is OfferPilot (demo — synthetic data only).",
    "hi": "Namaste {name}! Yeh OfferPilot hai (demo — sirf synthetic data).",
    "pa": "Sat Sri Akal {name}! Eh OfferPilot hai (demo — sirf synthetic data).",
}


def format_offer_message(customer: Customer, offer: Offer) -> str:
    lang = customer.language if customer.language in LABEL_FIELD else "en"
    greeting = GREETING[lang].format(name=customer.name.split()[0])
    if offer.kind == "none":
        body = NO_OFFER_TEXT[lang]
    else:
        body = getattr(offer, LABEL_FIELD[lang]).format(pct=int(offer.value))
    return f"{greeting}\n\n{body}"
