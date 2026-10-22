"""Sanity checks for the synthetic data generator — not exhaustive statistics
(that's what data_validation.py's charts are for), just regression guards
that the simulation logic stays sane as it evolves."""
import random
from datetime import date, timedelta

import numpy as np
import pytest

from offerpilot.data_gen.constants import build_daily_multiplier
from offerpilot.data_gen.generate_events import simulate_customer
from offerpilot.data_gen.personas import PERSONA_PARAMS, assign_persona, assign_uplift_label, weighted_choice
from offerpilot.db.models import Customer

WINDOW_START = date(2026, 1, 1)
WINDOW_END = WINDOW_START + timedelta(days=364)
ALL_DATES = [WINDOW_START + timedelta(days=i) for i in range(365)]


@pytest.fixture(scope="module")
def platform_mult():
    return dict(zip(ALL_DATES, build_daily_multiplier(ALL_DATES)))


def make_customer(persona: str, city_tier: str = "tier2", signup_date: date | None = None) -> Customer:
    return Customer(
        id=1, name="Test", city="Ludhiana", city_tier=city_tier, language="en",
        signup_date=signup_date or WINDOW_START, persona=persona,
    )


def test_build_daily_multiplier_is_positive_and_right_length(platform_mult):
    values = list(platform_mult.values())
    assert len(values) == 365
    assert all(v > 0 for v in values)


def test_weighted_choice_respects_weights():
    random.seed(0)
    counts = {"a": 0, "b": 0}
    for _ in range(5000):
        counts[weighted_choice({"a": 0.9, "b": 0.1})] += 1
    assert counts["a"] > counts["b"] * 4  # roughly 9:1, generous tolerance


def test_assign_persona_and_uplift_label_are_valid():
    random.seed(0)
    for _ in range(50):
        persona = assign_persona()
        assert persona in PERSONA_PARAMS
        assert assign_uplift_label(persona) in {"persuadable", "sure-thing", "lost-cause", "do-not-disturb"}


def test_loyal_champion_generates_frequent_purchases(platform_mult):
    random.seed(1)
    np.random.seed(1)
    customer = make_customer("Loyal Champion")
    events, total_spend, last_purchase = simulate_customer(customer, WINDOW_START, WINDOW_END, platform_mult)

    purchases = [e for e in events if e.event_type == "purchase"]
    assert len(purchases) > 10  # ~3.2/month over a year should be well above this
    assert total_spend > 0
    assert last_purchase is not None
    for e in events:
        assert e.customer_id == customer.id
        assert WINDOW_START <= e.timestamp.date() <= WINDOW_END + timedelta(days=14)


def test_dormant_customer_generates_few_or_no_purchases(platform_mult):
    random.seed(2)
    np.random.seed(2)
    customer = make_customer("Dormant")
    events, _total_spend, _last_purchase = simulate_customer(customer, WINDOW_START, WINDOW_END, platform_mult)
    purchases = [e for e in events if e.event_type == "purchase"]
    assert len(purchases) <= 5  # purchase_rate_per_month=0.05 over a year


def test_purchase_amounts_are_within_sane_bounds(platform_mult):
    random.seed(3)
    np.random.seed(3)
    customer = make_customer("High-Value Returner")
    events, _total_spend, _last_purchase = simulate_customer(customer, WINDOW_START, WINDOW_END, platform_mult)
    for e in events:
        if e.event_type in ("purchase", "return"):
            assert 99 <= e.amount <= 25000


def test_signup_after_window_end_produces_no_events(platform_mult):
    customer = make_customer("Loyal Champion", signup_date=WINDOW_END + timedelta(days=5))
    events, total_spend, last_purchase = simulate_customer(customer, WINDOW_START, WINDOW_END, platform_mult)
    assert events == []
    assert total_spend == 0.0
    assert last_purchase is None
