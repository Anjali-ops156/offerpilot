"""The rules engine: loads rules/*.yaml, filters the offer catalogue down to
what a specific customer is allowed to receive (consent, abuse protection,
tier-aware fairness, category/value caps), and separately gates WHETHER
anything should be sent right now at all (quiet hours, frequency caps,
budget pacing). Phase 4 wraps these functions directly as agent tools —
`get_eligible_offers`, `check_budget` are named in the brief for a reason.

`pick_offer` is a simple deterministic picker (no AI) used by the bot until
Phase 4 adds the agent; it's built entirely out of the same primitives the
agent will use, so swapping it later is additive, not a rewrite.
"""
from datetime import datetime, timedelta

import yaml

from offerpilot.config import RULES_DIR
from offerpilot.db.models import Customer, SentOffer
from offerpilot.rules.schema import Limits, Offer, OfferCatalogue


def load_catalogue() -> OfferCatalogue:
    with open(RULES_DIR / "offer_catalogue.yaml", encoding="utf-8") as f:
        return OfferCatalogue(**yaml.safe_load(f))


def load_limits() -> Limits:
    """Merges limits.yaml + fairness.yaml + abuse.yaml — split into separate
    files for a marketing reader's sake, but one flat set of guardrails in code."""
    merged: dict = {}
    for filename in ("limits.yaml", "fairness.yaml", "abuse.yaml"):
        with open(RULES_DIR / filename, encoding="utf-8") as f:
            merged.update(yaml.safe_load(f) or {})
    return Limits(**merged)


def validate_offer(offer: Offer, limits: Limits, category: str | None = None) -> tuple[bool, str]:
    """The deterministic guardrail check. Every offer — rule-picked or
    AI-picked — must pass this before it is ever sent to a customer."""
    cap = limits.category_cap(category)
    if offer.kind == "percent_off" and offer.value > cap:
        return False, f"{offer.value}% exceeds the applicable discount cap ({cap}%)"
    if offer.kind == "flat_off_inr" and offer.value > limits.max_offer_value_inr:
        return False, f"Rs {offer.value} exceeds max_offer_value_inr (Rs {limits.max_offer_value_inr})"
    if offer.kind == "bonus_points" and offer.value * limits.points_to_inr > limits.max_offer_value_inr:
        return False, "points liability exceeds max_offer_value_inr"
    if offer.kind == "bogo" and offer.value > 100:
        return False, "bogo value is a % off the 2nd item and cannot exceed 100"
    return True, "ok"


def is_suspected_abuser(features: dict, limits: Limits) -> bool:
    """Behavioural flag only — NEVER derived from the hidden persona label.
    A real platform can only see coupon/return behaviour, not a secret tag."""
    return (
        features.get("discount_sensitivity", 0.0) > limits.abuse_coupon_rate_threshold
        or features.get("return_rate", 0.0) > limits.abuse_return_rate_threshold
    )


def _tier_adjusted_win_back(offer: Offer, loyalty_tier: str | None, limits: Limits) -> Offer:
    pct = limits.win_back_discount_pct_by_tier.get(loyalty_tier or "bronze", offer.value)
    return offer.model_copy(update={"value": pct})


def get_eligible_offers(customer: Customer, features: dict, catalogue: OfferCatalogue, limits: Limits) -> list[Offer]:
    """WHAT a customer is allowed to receive, content-wise. Does not check
    quiet hours / frequency / budget — see can_send_now() for that."""
    if limits.require_consent and not customer.consent_opt_in:
        return [catalogue.get("no_offer")]

    abuser = is_suspected_abuser(features, limits)

    eligible: list[Offer] = []
    for offer in catalogue.offers:
        candidate = offer
        if offer.type == "win_back_discount":
            candidate = _tier_adjusted_win_back(offer, customer.loyalty_tier, limits)
        if offer.type == "bonus_points" and customer.reward_points_balance < limits.gold_points_bonus_threshold:
            continue
        if abuser and candidate.kind not in limits.abuse_allowed_offer_kinds:
            continue
        # category_discount_caps applies to offers explicitly scoped to one category
        # (none are, yet — see rules/fairness.yaml) via validate_offer(..., category=...),
        # NOT to the customer's favourite category: capping a generic, order-wide offer
        # by "what this customer happens to buy most" would undercut the tier-fairness
        # guarantee above (a gold customer whose favourite category is capped tighter
        # than their tier discount would get silently downgraded).
        ok, _reason = validate_offer(candidate, limits, category=None)
        if ok:
            eligible.append(candidate)
    return eligible


def is_quiet_hours(now: datetime, limits: Limits) -> bool:
    start, end = limits.quiet_hours_start_ist, limits.quiet_hours_end_ist
    hour = now.hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end  # wraps past midnight, e.g. 22 -> 8


def check_frequency(
    session, customer_id: int, limits: Limits, now: datetime, max_offers_per_week: int | None = None,
) -> tuple[bool, str]:
    """max_offers_per_week: a customer's own /preferences override, if set —
    always the SMALLER of it and the platform cap; a customer can ask for
    fewer offers, never more than the platform allows."""
    effective_weekly_cap = min(limits.max_offers_per_week, max_offers_per_week or limits.max_offers_per_week)

    recent = (
        session.query(SentOffer)
        .filter(
            SentOffer.customer_id == customer_id,
            SentOffer.sent_at >= now - timedelta(days=7),
            SentOffer.sent_at <= now,  # defensive: a clock-skewed or simulated future row must never count
        )
        .all()
    )
    today_count = sum(1 for s in recent if s.sent_at >= now - timedelta(days=1))
    if today_count >= limits.max_offers_per_day:
        return False, f"max_offers_per_day ({limits.max_offers_per_day}) already reached"
    if len(recent) >= effective_weekly_cap:
        return False, f"max_offers_per_week ({effective_weekly_cap}) already reached"
    if recent:
        last_sent = max(s.sent_at for s in recent)
        if now - last_sent < timedelta(days=limits.cooldown_days_after_offer):
            return False, f"cooldown_days_after_offer ({limits.cooldown_days_after_offer}) not yet elapsed"
    return True, "ok"


def check_budget(session, limits: Limits, proposed_cost_inr: float, now: datetime) -> tuple[bool, str]:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    spent_today = (
        session.query(SentOffer).filter(SentOffer.sent_at >= day_start, SentOffer.sent_at <= now).all()
    )
    spent_today_total = sum(s.cost_inr for s in spent_today)
    if spent_today_total + proposed_cost_inr > limits.daily_budget_inr:
        return False, f"would exceed daily_budget_inr (Rs {limits.daily_budget_inr})"

    spent_month = session.query(SentOffer).filter(SentOffer.sent_at >= month_start, SentOffer.sent_at <= now).all()
    spent_month_total = sum(s.cost_inr for s in spent_month)
    if spent_month_total + proposed_cost_inr > limits.campaign_budget_inr:
        return False, f"would exceed campaign_budget_inr (Rs {limits.campaign_budget_inr})"
    return True, "ok"


def can_send_now(
    session, customer_id: int, limits: Limits, proposed_cost_inr: float, now: datetime,
    respect_quiet_hours: bool = True, max_offers_per_week: int | None = None,
) -> tuple[bool, str]:
    """respect_quiet_hours=False for a PULL interaction (a classmate opening
    the bot themselves via /start) — quiet hours exists to stop unsolicited
    PUSH notifications at night, not to refuse someone who's already here.
    Frequency caps, cooldown, and budget apply either way.
    max_offers_per_week: the customer's own /preferences override, if set."""
    if respect_quiet_hours and is_quiet_hours(now, limits):
        return False, "quiet hours"
    ok, reason = check_frequency(session, customer_id, limits, now, max_offers_per_week)
    if not ok:
        return False, reason
    return check_budget(session, limits, proposed_cost_inr, now)


def record_sent_offer(session, customer_id: int, offer_type: str, cost_inr: float, sent_at: datetime) -> None:
    session.add(SentOffer(customer_id=customer_id, offer_type=offer_type, sent_at=sent_at, cost_inr=cost_inr))
    session.commit()


def pick_offer(customer: Customer, features: dict, catalogue: OfferCatalogue, limits: Limits) -> Offer:
    """Simple deterministic rule, not AI — same priority order as the thin
    slice, now filtered through the full eligibility pipeline above."""
    eligible = get_eligible_offers(customer, features, catalogue, limits)
    eligible_types = {o.type for o in eligible}

    if customer.days_since_last_purchase >= limits.win_back_days_threshold and "win_back_discount" in eligible_types:
        return next(o for o in eligible if o.type == "win_back_discount")
    if "bonus_points" in eligible_types:
        return next(o for o in eligible if o.type == "bonus_points")
    if "free_shipping" in eligible_types:
        return next(o for o in eligible if o.type == "free_shipping")
    return catalogue.get("no_offer")
