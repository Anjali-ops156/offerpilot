"""Rule-based offer picker + the guardrail check every offer must pass.

This is deliberately simple logic for now (no AI yet — see roadmap Phase 4).
`validate_offer` is written so the future AI agent's picks can be run through
the exact same function: the rules are the single source of truth either way.
"""
import yaml

from offerpilot.config import RULES_DIR
from offerpilot.db.models import Customer
from offerpilot.rules.schema import Limits, Offer, OfferCatalogue


def load_catalogue() -> OfferCatalogue:
    with open(RULES_DIR / "offer_catalogue.yaml", encoding="utf-8") as f:
        return OfferCatalogue(**yaml.safe_load(f))


def load_limits() -> Limits:
    with open(RULES_DIR / "limits.yaml", encoding="utf-8") as f:
        return Limits(**yaml.safe_load(f))


def validate_offer(offer: Offer, limits: Limits) -> tuple[bool, str]:
    """The deterministic guardrail check. Every offer — rule-picked or AI-picked —
    must pass this before it is ever sent to a customer."""
    if offer.kind == "percent_off" and offer.value > limits.max_discount_pct:
        return False, f"{offer.value}% exceeds max_discount_pct ({limits.max_discount_pct}%)"
    if offer.kind == "flat_off_inr" and offer.value > limits.max_offer_value_inr:
        return False, f"₹{offer.value} exceeds max_offer_value_inr (₹{limits.max_offer_value_inr})"
    return True, "ok"


def pick_offer(customer: Customer, catalogue: OfferCatalogue, limits: Limits) -> Offer:
    """Simple deterministic rule, not AI. Picks one offer (or 'no_offer' — silence
    is a valid decision) based on the customer's eligibility."""
    if limits.require_consent and not customer.consent_opt_in:
        return catalogue.get("no_offer")

    if customer.days_since_last_purchase >= limits.win_back_days_threshold:
        candidate = catalogue.get("win_back_discount")
    elif (
        customer.loyalty_tier == "gold"
        and customer.reward_points_balance >= limits.gold_points_bonus_threshold
    ):
        candidate = catalogue.get("bonus_points")
    else:
        candidate = catalogue.get("free_shipping")

    ok, _reason = validate_offer(candidate, limits)
    return candidate if ok else catalogue.get("no_offer")
