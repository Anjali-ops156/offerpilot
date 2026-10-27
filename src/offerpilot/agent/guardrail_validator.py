"""The deterministic final authority. Every AI-proposed (offer, message)
pair passes through here before anything is ever sent — this is what makes
the agent's output trustworthy regardless of what the model decided to do.

Checks, in order:
  1. The offer is actually in this customer's ELIGIBLE set right now (not
     just "a valid catalogue entry" — consent, abuse restriction, category/
     value caps, tier-fairness all apply, via rules.engine.get_eligible_offers).
  2. Sending anything at all is allowed right now (frequency cap, cooldown,
     budget — rules.engine.can_send_now).
  3. The message doesn't invent a discount/price different from the actual
     offer (the model must quote the REAL number, not a made-up one).
  4. No forbidden pressure-tactic phrasing (rules/fairness.yaml).
  5. No leaked internal terminology (persona/uplift labels) — a message
     must never expose the hidden scores behind a decision.
  6. The message isn't empty, isn't absurdly short/long.
"""
from datetime import datetime

from offerpilot.db.models import Customer
from offerpilot.features.next_best_action import offer_cost_inr
from offerpilot.rules.engine import can_send_now, get_eligible_offers
from offerpilot.rules.schema import Limits, Offer, OfferCatalogue

MIN_MESSAGE_LEN = 10
MAX_MESSAGE_LEN = 600

LEAKED_INTERNAL_TERMS = [
    "persona", "uplift_label", "uplift label", "sure-thing", "lost-cause",
    "do-not-disturb", "persuadable", "churn risk", "churn_risk", "clv",
]


def _offer_amount_is_quoted_correctly(offer: Offer, message: str) -> bool:
    if offer.kind == "percent_off":
        return f"{int(offer.value)}%" in message
    if offer.kind == "flat_off_inr":
        return str(int(offer.value)) in message
    if offer.kind == "bonus_points":
        return str(int(offer.value)) in message
    return True  # free_shipping / bogo / early_access / nudge / none carry no quotable figure to fabricate


def validate_submission(
    customer: Customer, features: dict, offer_type: str, message: str,
    catalogue: OfferCatalogue, limits: Limits, session, now: datetime,
) -> tuple[bool, str, Offer | None]:
    eligible = {o.type: o for o in get_eligible_offers(customer, features, catalogue, limits)}
    if offer_type not in eligible:
        return False, f"'{offer_type}' is not currently eligible for this customer (consent/abuse/cap/fairness filter)", None
    offer = eligible[offer_type]

    expected_order_value = features.get("avg_order_value") or 1000.0
    cost = offer_cost_inr(expected_order_value, offer, limits)
    ok, reason = can_send_now(session, customer.id, limits, cost, now, respect_quiet_hours=False)
    if not ok:
        return False, f"cannot send right now: {reason}", None

    if not message or not message.strip():
        return False, "message is empty", None
    if not (MIN_MESSAGE_LEN <= len(message) <= MAX_MESSAGE_LEN):
        return False, f"message length {len(message)} is outside [{MIN_MESSAGE_LEN}, {MAX_MESSAGE_LEN}]", None

    lowered = message.lower()
    for phrase in limits.forbidden_pressure_phrases:
        if phrase.lower() in lowered:
            return False, f"message contains a forbidden pressure-tactic phrase: '{phrase}'", None
    for term in LEAKED_INTERNAL_TERMS:
        if term in lowered:
            return False, f"message leaks an internal term that must never reach the customer: '{term}'", None

    if not _offer_amount_is_quoted_correctly(offer, message):
        return False, (
            f"message doesn't quote the actual offer value ({offer.value} for kind {offer.kind}) — "
            "possible fabricated discount"
        ), None

    return True, "ok", offer
