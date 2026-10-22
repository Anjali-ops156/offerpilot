import pytest

from offerpilot.db.models import Customer
from offerpilot.rules.engine import load_catalogue, load_limits, pick_offer, validate_offer
from offerpilot.rules.schema import Offer


@pytest.fixture(scope="module")
def catalogue():
    return load_catalogue()


@pytest.fixture(scope="module")
def limits():
    return load_limits()


def make_customer(**overrides) -> Customer:
    defaults = dict(
        name="Test Customer",
        city="Ludhiana",
        city_tier="tier2",
        language="en",
        loyalty_tier="bronze",
        reward_points_balance=0,
        consent_opt_in=True,
        days_since_last_purchase=5,
        total_spend=1000.0,
    )
    defaults.update(overrides)
    return Customer(**defaults)


def test_no_consent_means_no_offer(catalogue, limits):
    customer = make_customer(consent_opt_in=False, days_since_last_purchase=90)
    offer = pick_offer(customer, catalogue, limits)
    assert offer.type == "no_offer"


def test_inactive_customer_gets_win_back_discount(catalogue, limits):
    customer = make_customer(days_since_last_purchase=limits.win_back_days_threshold)
    offer = pick_offer(customer, catalogue, limits)
    assert offer.type == "win_back_discount"


def test_gold_customer_with_points_gets_bonus_points(catalogue, limits):
    customer = make_customer(
        loyalty_tier="gold",
        reward_points_balance=limits.gold_points_bonus_threshold,
        days_since_last_purchase=1,
    )
    offer = pick_offer(customer, catalogue, limits)
    assert offer.type == "bonus_points"


def test_default_active_customer_gets_free_shipping(catalogue, limits):
    customer = make_customer(days_since_last_purchase=1, loyalty_tier="bronze")
    offer = pick_offer(customer, catalogue, limits)
    assert offer.type == "free_shipping"


def test_validate_offer_rejects_discount_above_cap(limits):
    too_generous = Offer(
        type="rogue", kind="percent_off", value=limits.max_discount_pct + 1,
        label_en="x", label_hi="x", label_pa="x",
    )
    ok, reason = validate_offer(too_generous, limits)
    assert ok is False
    assert "exceeds" in reason


def test_validate_offer_accepts_catalogue_offers(catalogue, limits):
    for offer in catalogue.offers:
        ok, reason = validate_offer(offer, limits)
        assert ok is True, f"{offer.type} unexpectedly failed: {reason}"
