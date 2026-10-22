"""Next-best-action scoring: score = P(uplift) x expected margin - offer cost.

This is the economics layer that sits between the uplift model and the
rules engine's guardrails. Phase 4 wraps `simulate_margin` and
`next_best_action_score` directly as agent tools — the logic here IS what
`estimate_uplift` / `simulate_margin` / `submit_offer` will call.
"""
from dataclasses import dataclass

from offerpilot.rules.schema import Limits, Offer


def offer_cost_inr(expected_order_value: float, offer: Offer, limits: Limits) -> float:
    """What this offer costs us if the customer takes it."""
    if offer.kind == "percent_off":
        return expected_order_value * offer.value / 100
    if offer.kind == "flat_off_inr":
        return offer.value
    if offer.kind == "free_shipping":
        return limits.shipping_cost_inr
    if offer.kind == "bonus_points":
        return offer.value * limits.points_to_inr
    if offer.kind == "bogo":
        return expected_order_value * 0.5 * offer.value / 100  # value = % off the 2nd item
    # "early_access" and "nudge" (cart_recovery_nudge, points_expiry_reminder) carry no
    # direct monetary cost; "none" is silence.
    return 0.0  # "none"


@dataclass
class MarginSimulation:
    expected_order_value: float
    gross_margin_inr: float
    offer_cost_inr: float
    net_margin_inr: float  # gross margin AFTER absorbing the offer's cost
    net_margin_pct: float  # net margin as a % of order value — checked against min_margin_floor_pct


def simulate_margin(expected_order_value: float, offer: Offer, limits: Limits) -> MarginSimulation:
    expected_order_value = max(expected_order_value, 0.0)
    gross_margin = expected_order_value * limits.gross_margin_pct / 100
    cost = offer_cost_inr(expected_order_value, offer, limits)
    net_margin = gross_margin - cost
    net_margin_pct = (net_margin / expected_order_value * 100) if expected_order_value > 0 else 0.0
    return MarginSimulation(
        expected_order_value=expected_order_value,
        gross_margin_inr=round(gross_margin, 2),
        offer_cost_inr=round(cost, 2),
        net_margin_inr=round(net_margin, 2),
        net_margin_pct=round(net_margin_pct, 2),
    )


@dataclass
class NextBestActionScore:
    offer_type: str
    uplift: float
    margin: MarginSimulation
    score: float  # uplift x gross_margin - offer_cost


def next_best_action_score(uplift: float, expected_order_value: float, offer: Offer, limits: Limits) -> NextBestActionScore:
    margin = simulate_margin(expected_order_value, offer, limits)
    score = uplift * margin.gross_margin_inr - margin.offer_cost_inr
    return NextBestActionScore(offer_type=offer.type, uplift=uplift, margin=margin, score=round(score, 2))


def rank_offers(
    uplift_by_offer: dict[str, float], expected_order_value: float, offers: list[Offer], limits: Limits
) -> list[NextBestActionScore]:
    """Highest score first. `uplift_by_offer` maps offer_type -> predicted
    uplift for sending THAT offer (a "none" entry should be 0 — no offer,
    no incremental effect, but also no cost, so it scores 0 and acts as the
    baseline every other offer has to beat)."""
    scored = [
        next_best_action_score(uplift_by_offer.get(offer.type, 0.0), expected_order_value, offer, limits)
        for offer in offers
    ]
    return sorted(scored, key=lambda s: s.score, reverse=True)
