from typing import Literal

from pydantic import BaseModel, Field

OfferKind = Literal["percent_off", "flat_off_inr", "free_shipping", "bonus_points", "none"]


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
    max_discount_pct: float = Field(gt=0)
    min_margin_floor_pct: float = Field(ge=0)
    max_offer_value_inr: float = Field(gt=0)
    win_back_days_threshold: int = Field(gt=0)
    gold_points_bonus_threshold: int = Field(ge=0)
    quiet_hours_start_ist: int = Field(ge=0, le=23)
    quiet_hours_end_ist: int = Field(ge=0, le=23)
    require_consent: bool = True
