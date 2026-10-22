from typing import Literal

from pydantic import BaseModel, Field

OfferKind = Literal[
    "percent_off", "flat_off_inr", "free_shipping", "bonus_points",
    "bogo", "early_access", "nudge", "none",
]
LoyaltyTier = Literal["bronze", "silver", "gold"]


class Offer(BaseModel):
    type: str
    kind: OfferKind
    value: float
    label_en: str
    label_hi: str
    label_pa: str


class OfferCatalogue(BaseModel):
    offers: list[Offer]

    def get(self, offer_type: str) -> Offer:
        for offer in self.offers:
            if offer.type == offer_type:
                return offer
        raise KeyError(f"Unknown offer type: {offer_type}")


class Limits(BaseModel):
    # Core discount/margin/offer-value caps.
    max_discount_pct: float = Field(gt=0)
    min_margin_floor_pct: float = Field(ge=0)
    max_offer_value_inr: float = Field(gt=0)
    win_back_days_threshold: int = Field(gt=0)
    gold_points_bonus_threshold: int = Field(ge=0)
    quiet_hours_start_ist: int = Field(ge=0, le=23)
    quiet_hours_end_ist: int = Field(ge=0, le=23)
    require_consent: bool = True

    # Economics assumptions for next-best-action scoring.
    gross_margin_pct: float = Field(ge=0, le=100, default=35)
    shipping_cost_inr: float = Field(ge=0, default=60)
    points_to_inr: float = Field(ge=0, default=0.5)

    # Spend pacing + frequency caps (rules/limits.yaml).
    daily_budget_inr: float = Field(gt=0, default=15000)
    campaign_budget_inr: float = Field(gt=0, default=400000)
    max_offers_per_day: int = Field(gt=0, default=1)
    max_offers_per_week: int = Field(gt=0, default=2)
    cooldown_days_after_offer: int = Field(ge=0, default=3)

    # Fairness (rules/fairness.yaml).
    win_back_discount_pct_by_tier: dict[LoyaltyTier, float] = Field(
        default_factory=lambda: {"gold": 20, "silver": 17, "bronze": 15}
    )
    category_discount_caps: dict[str, float] = Field(default_factory=dict)
    forbidden_pressure_phrases: list[str] = Field(default_factory=list)

    # Abuse protection (rules/abuse.yaml).
    abuse_coupon_rate_threshold: float = Field(ge=0, le=1, default=0.75)
    abuse_return_rate_threshold: float = Field(ge=0, le=1, default=0.35)
    abuse_allowed_offer_kinds: list[OfferKind] = Field(
        default_factory=lambda: ["free_shipping", "early_access", "nudge", "none"]
    )

    def category_cap(self, category: str | None) -> float:
        """The effective max_discount_pct for a category — the smaller of
        the global cap and any category-specific cap."""
        if category and category in self.category_discount_caps:
            return min(self.max_discount_pct, self.category_discount_caps[category])
        return self.max_discount_pct
