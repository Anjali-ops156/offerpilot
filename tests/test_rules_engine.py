import pytest

from offerpilot.db.models import Customer
from offerpilot.rules.engine import get_eligible_offers, load_catalogue, load_limits, pick_offer, validate_offer
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


NO_SIGNAL_FEATURES: dict = {}  # discount_sensitivity / return_rate default to 0.0 -> never flagged as abuse


def test_no_consent_means_no_offer(catalogue, limits):
    customer = make_customer(consent_opt_in=False, days_since_last_purchase=90)
    offer = pick_offer(customer, NO_SIGNAL_FEATURES, catalogue, limits)
    assert offer.type == "no_offer"


def test_inactive_customer_gets_win_back_discount(catalogue, limits):
    customer = make_customer(days_since_last_purchase=limits.win_back_days_threshold)
    offer = pick_offer(customer, NO_SIGNAL_FEATURES, catalogue, limits)
    assert offer.type == "win_back_discount"


def test_gold_customer_with_points_gets_bonus_points(catalogue, limits):
    customer = make_customer(
        loyalty_tier="gold",
        reward_points_balance=limits.gold_points_bonus_threshold,
        days_since_last_purchase=1,
    )
    offer = pick_offer(customer, NO_SIGNAL_FEATURES, catalogue, limits)
    assert offer.type == "bonus_points"


def test_default_active_customer_gets_free_shipping(catalogue, limits):
    customer = make_customer(days_since_last_purchase=1, loyalty_tier="bronze")
    offer = pick_offer(customer, NO_SIGNAL_FEATURES, catalogue, limits)
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


# --- Fairness -----------------------------------------------------------

def test_gold_win_back_is_never_worse_than_bronze(catalogue, limits):
    gold = make_customer(loyalty_tier="gold", days_since_last_purchase=limits.win_back_days_threshold)
    bronze = make_customer(loyalty_tier="bronze", days_since_last_purchase=limits.win_back_days_threshold)

    gold_offer = pick_offer(gold, NO_SIGNAL_FEATURES, catalogue, limits)
    bronze_offer = pick_offer(bronze, NO_SIGNAL_FEATURES, catalogue, limits)

    assert gold_offer.type == bronze_offer.type == "win_back_discount"
    assert gold_offer.value >= bronze_offer.value


def test_offer_decision_never_reads_gender_or_raw_city(catalogue, limits):
    """Fairness by construction: two customers who differ ONLY in gender, or
    ONLY in raw city (same city_tier), must get the identical offer."""
    base = dict(days_since_last_purchase=limits.win_back_days_threshold, loyalty_tier="silver")
    a = make_customer(gender="F", city="Ludhiana", **base)
    b = make_customer(gender="M", city="Amritsar", **base)  # both tier2

    offer_a = pick_offer(a, NO_SIGNAL_FEATURES, catalogue, limits)
    offer_b = pick_offer(b, NO_SIGNAL_FEATURES, catalogue, limits)
    assert offer_a == offer_b


# --- Abuse protection -----------------------------------------------------

def test_suspected_coupon_abuser_is_restricted_to_zero_cost_offers(catalogue, limits):
    customer = make_customer(days_since_last_purchase=limits.win_back_days_threshold, loyalty_tier="gold")
    abuser_features = {"discount_sensitivity": limits.abuse_coupon_rate_threshold + 0.1, "return_rate": 0.0}

    eligible = get_eligible_offers(customer, abuser_features, catalogue, limits)
    assert eligible  # still gets SOMETHING, just nothing costly
    assert all(o.kind in limits.abuse_allowed_offer_kinds for o in eligible)
    assert not any(o.kind == "percent_off" for o in eligible)


def test_normal_customer_is_not_restricted(catalogue, limits):
    customer = make_customer(days_since_last_purchase=limits.win_back_days_threshold)
    eligible = get_eligible_offers(customer, NO_SIGNAL_FEATURES, catalogue, limits)
    assert any(o.kind == "percent_off" for o in eligible)
