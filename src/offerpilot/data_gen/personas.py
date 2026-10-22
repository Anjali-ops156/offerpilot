"""Hidden ground truth: persona + latent uplift label, and the behavioural
parameters used to SIMULATE each persona's events.

IMPORTANT: nothing in `offerpilot.rules`, `offerpilot.agent`, or `offerpilot.bot`
may import this module or read Customer.persona / Customer.latent_uplift_label.
These exist only so Phase 6 can score how well the (persona/label-blind)
decision engine actually performed.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

UPLIFT_LABELS = ["persuadable", "sure-thing", "lost-cause", "do-not-disturb"]

# temporal shape of a persona's activity across their eligible window:
#   flat          - steady all year
#   declining      - rising churn hazard; tapers from 1.0 to a low floor
#   sparse_tail    - active early, then goes quiet (explains a long recency)
#   new_ramp       - short tenure, activity ramps up since signup
TemporalShape = str


@dataclass(frozen=True)
class PersonaParams:
    weight: float  # share of the customer population
    purchase_rate_per_month: float
    aov_mean: float  # mean order value, INR
    aov_sigma: float  # lognormal sigma (spread)
    return_rate: float  # base probability a purchase is returned
    coupon_use_rate: float  # probability a purchase uses a coupon
    session_multiplier: float  # sessions per purchase (funnel width)
    temporal_shape: TemporalShape
    loyalty_tier_weights: dict[str, float]
    uplift_dist: dict[str, float] = field(default_factory=dict)


PERSONA_PARAMS: dict[str, PersonaParams] = {
    "Loyal Champion": PersonaParams(
        weight=0.12, purchase_rate_per_month=3.2, aov_mean=1800, aov_sigma=0.45,
        return_rate=0.08, coupon_use_rate=0.15, session_multiplier=4.0,
        temporal_shape="flat",
        loyalty_tier_weights={"gold": 0.7, "silver": 0.25, "bronze": 0.05},
        uplift_dist={"sure-thing": 0.6, "persuadable": 0.3, "lost-cause": 0.05, "do-not-disturb": 0.05},
    ),
    "Deal Hunter": PersonaParams(
        weight=0.15, purchase_rate_per_month=1.8, aov_mean=900, aov_sigma=0.55,
        return_rate=0.12, coupon_use_rate=0.65, session_multiplier=5.0,
        temporal_shape="flat",
        loyalty_tier_weights={"silver": 0.5, "bronze": 0.35, "gold": 0.15},
        uplift_dist={"persuadable": 0.55, "sure-thing": 0.15, "lost-cause": 0.2, "do-not-disturb": 0.1},
    ),
    "At-Risk": PersonaParams(
        weight=0.13, purchase_rate_per_month=0.6, aov_mean=1200, aov_sigma=0.5,
        return_rate=0.10, coupon_use_rate=0.25, session_multiplier=3.0,
        temporal_shape="declining",
        loyalty_tier_weights={"silver": 0.45, "bronze": 0.35, "gold": 0.2},
        uplift_dist={"persuadable": 0.5, "lost-cause": 0.3, "sure-thing": 0.1, "do-not-disturb": 0.1},
    ),
    "Dormant": PersonaParams(
        weight=0.15, purchase_rate_per_month=0.05, aov_mean=1000, aov_sigma=0.5,
        return_rate=0.10, coupon_use_rate=0.2, session_multiplier=2.0,
        temporal_shape="sparse_tail",
        loyalty_tier_weights={"bronze": 0.6, "silver": 0.3, "gold": 0.1},
        uplift_dist={"lost-cause": 0.45, "persuadable": 0.35, "do-not-disturb": 0.15, "sure-thing": 0.05},
    ),
    "New Explorer": PersonaParams(
        weight=0.15, purchase_rate_per_month=0.9, aov_mean=700, aov_sigma=0.6,
        return_rate=0.15, coupon_use_rate=0.4, session_multiplier=4.5,
        temporal_shape="new_ramp",
        loyalty_tier_weights={"bronze": 0.85, "silver": 0.15},
        uplift_dist={"persuadable": 0.45, "sure-thing": 0.25, "lost-cause": 0.2, "do-not-disturb": 0.1},
    ),
    "Window Shopper": PersonaParams(
        weight=0.12, purchase_rate_per_month=0.15, aov_mean=600, aov_sigma=0.5,
        return_rate=0.10, coupon_use_rate=0.3, session_multiplier=14.0,
        temporal_shape="flat",
        loyalty_tier_weights={"bronze": 0.7, "silver": 0.3},
        uplift_dist={"lost-cause": 0.4, "persuadable": 0.35, "do-not-disturb": 0.15, "sure-thing": 0.1},
    ),
    "Coupon Abuser": PersonaParams(
        weight=0.08, purchase_rate_per_month=1.5, aov_mean=800, aov_sigma=0.4,
        return_rate=0.35, coupon_use_rate=0.9, session_multiplier=3.5,
        temporal_shape="flat",
        loyalty_tier_weights={"bronze": 0.5, "silver": 0.4, "gold": 0.1},
        uplift_dist={"do-not-disturb": 0.5, "sure-thing": 0.3, "persuadable": 0.1, "lost-cause": 0.1},
    ),
    "High-Value Returner": PersonaParams(
        weight=0.10, purchase_rate_per_month=2.5, aov_mean=2500, aov_sigma=0.5,
        return_rate=0.40, coupon_use_rate=0.2, session_multiplier=3.5,
        temporal_shape="flat",
        loyalty_tier_weights={"gold": 0.5, "silver": 0.4, "bronze": 0.1},
        uplift_dist={"sure-thing": 0.5, "persuadable": 0.2, "do-not-disturb": 0.2, "lost-cause": 0.1},
    ),
}

PERSONAS = list(PERSONA_PARAMS)


def weighted_choice(options: dict[str, float]) -> str:
    names = list(options)
    weights = list(options.values())
    return random.choices(names, weights=weights, k=1)[0]


def assign_persona() -> str:
    return weighted_choice({p: params.weight for p, params in PERSONA_PARAMS.items()})


def assign_uplift_label(persona: str) -> str:
    return weighted_choice(PERSONA_PARAMS[persona].uplift_dist)


def assign_loyalty_tier(persona: str) -> str:
    return weighted_choice(PERSONA_PARAMS[persona].loyalty_tier_weights)
