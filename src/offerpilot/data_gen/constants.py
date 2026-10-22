"""Shared, non-hidden constants for the synthetic data generator: geography,
product categories, and the recurring calendar effects (festivals, salary
days, weekly cycle) that drive seasonality in event volume.

None of this module encodes hidden ground truth — see personas.py for that.
"""
from __future__ import annotations

from datetime import date, timedelta

WINDOW_DAYS = 365


def default_window(end: date | None = None) -> tuple[date, date]:
    """The 12-month event-generation window: [start, end], inclusive."""
    end = end or date.today()
    start = end - timedelta(days=WINDOW_DAYS - 1)
    return start, end

CITY_TIERS: dict[str, str] = {
    "Chandigarh": "metro",
    "Delhi NCR": "metro",
    "Ludhiana": "tier2",
    "Amritsar": "tier2",
    "Jalandhar": "tier2",
    "Patiala": "tier2",
    "Bathinda": "tier3",
    "Moga": "tier3",
    "Hoshiarpur": "tier3",
}

# Tier-3 towns skew Cash-on-Delivery far more than metros (brief: "higher COD
# share in tier-3 towns").
COD_PROBABILITY_BY_TIER: dict[str, float] = {"metro": 0.20, "tier2": 0.38, "tier3": 0.58}

# Zipf-style long-tail popularity: a handful of categories dominate, the rest
# have a long tail. Weights are relative, not normalised.
CATEGORIES: dict[str, float] = {
    "Fashion": 100,
    "Mobile Accessories": 70,
    "Beauty & Personal Care": 55,
    "Home & Kitchen": 45,
    "Footwear": 38,
    "Electronics": 32,
    "Groceries": 28,
    "Jewellery": 18,
    "Sports": 14,
    "Books": 9,
    "Toys": 7,
    "Furniture": 5,
}

# Fashion (and to a lesser extent footwear/jewellery — fit/sizing/gifting
# issues) returns far more than the rest (brief: "high return rates in fashion").
CATEGORY_RETURN_MULTIPLIER: dict[str, float] = {
    "Fashion": 2.2,
    "Footwear": 1.6,
    "Jewellery": 1.3,
    "Electronics": 0.8,
    "Mobile Accessories": 0.7,
    "Beauty & Personal Care": 0.6,
    "Groceries": 0.2,
    "Books": 0.3,
}
DEFAULT_RETURN_MULTIPLIER = 1.0


def category_weights() -> tuple[list[str], list[float]]:
    names = list(CATEGORIES)
    weights = list(CATEGORIES.values())
    return names, weights


# Recurring calendar effects, expressed as (month, day) spans so they apply in
# any year the 12-month generation window happens to cover — no hardcoded
# absolute dates to go stale.
# (start_month, start_day, end_month, end_day, multiplier, label)
FESTIVAL_WINDOWS: list[tuple[int, int, int, int, float, str]] = [
    (1, 12, 1, 14, 2.0, "Lohri"),
    (1, 24, 1, 27, 2.3, "Republic Day sale"),
    (4, 12, 4, 15, 1.8, "Baisakhi"),
    (10, 1, 10, 8, 3.0, "Big-Billion-style sale"),
    (10, 14, 10, 21, 1.7, "Karva Chauth"),
    (10, 17, 11, 2, 3.3, "Diwali"),
]
# Broad wedding-season uplift (lower multiplier, longer span) layered under
# the sharper festival spikes above.
WEDDING_SEASON = (11, 15, 2, 15, 1.3)


def _in_month_day_span(d: date, start_month: int, start_day: int, end_month: int, end_day: int) -> bool:
    """True if d falls in the month/day span, handling spans that wrap past
    year-end (e.g. wedding season Nov->Feb)."""
    start = (start_month, start_day)
    end = (end_month, end_day)
    md = (d.month, d.day)
    if start <= end:
        return start <= md <= end
    return md >= start or md <= end


def build_daily_multiplier(dates: list[date]) -> list[float]:
    """Platform-wide activity multiplier per day: weekly cycle * salary-day
    bump * the strongest overlapping festival/wedding-season effect."""
    multipliers = []
    for d in dates:
        # Weekend shopping bump, soft Monday dip.
        weekday = d.weekday()  # 0=Mon ... 6=Sun
        if weekday in (4, 5, 6):  # Fri/Sat/Sun
            weekly = 1.3
        elif weekday == 0:
            weekly = 0.9
        else:
            weekly = 1.0

        # Salary-day bump: first few days and last few days of the month.
        last_day_of_month = (date(d.year, d.month, 28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        salary = 1.4 if d.day <= 3 or d.day >= last_day_of_month.day - 2 else 1.0

        festival = 1.0
        for sm, sd, em, ed, mult, _label in FESTIVAL_WINDOWS:
            if _in_month_day_span(d, sm, sd, em, ed):
                festival = max(festival, mult)
        if _in_month_day_span(d, *WEDDING_SEASON[:4]):
            festival = max(festival, WEDDING_SEASON[4])

        multipliers.append(weekly * salary * festival)
    return multipliers
