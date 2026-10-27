from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from offerpilot.bot.handlers import _apply_simulation
from offerpilot.db.models import Base, Customer, Event
from offerpilot.rules.engine import load_limits


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture(scope="module")
def limits():
    return load_limits()


def make_customer(**overrides) -> Customer:
    defaults = dict(
        id=1, name="Test User", city="Ludhiana", city_tier="tier2", language="en",
        loyalty_tier="bronze", reward_points_balance=0, consent_opt_in=True,
        days_since_last_purchase=5, total_spend=1000.0,
    )
    defaults.update(overrides)
    return Customer(**defaults)


def test_abandon_cart_inserts_real_events(session, limits):
    customer = make_customer()
    session.add(customer)
    session.commit()
    now = datetime(2026, 1, 1, 14, 0)

    preview_customer, preview_features, intro_key = _apply_simulation(customer, {}, "abandon_cart", session, now, limits)

    events = session.query(Event).filter_by(customer_id=1).all()
    assert {e.event_type for e in events} == {"add_to_cart", "cart_abandon"}
    assert intro_key == "simulate_abandon_cart_intro"
    assert preview_customer is customer  # real customer, nothing cloned


def test_go_inactive_does_not_touch_the_real_customer_row(session, limits):
    customer = make_customer(days_since_last_purchase=3)
    session.add(customer)
    session.commit()
    now = datetime(2026, 1, 1, 14, 0)

    preview_customer, preview_features, intro_key = _apply_simulation(customer, {}, "go_inactive", session, now, limits)

    assert preview_customer.days_since_last_purchase == limits.win_back_days_threshold + 1
    assert preview_features["recency_days"] == limits.win_back_days_threshold + 1
    assert customer.days_since_last_purchase == 3  # untouched
    assert intro_key == "simulate_go_inactive_intro"


def test_points_expiring_does_not_touch_the_real_customer_row(session, limits):
    customer = make_customer(reward_points_balance=0)
    session.add(customer)
    session.commit()
    now = datetime(2026, 1, 1, 14, 0)

    preview_customer, _features, intro_key = _apply_simulation(customer, {}, "points_expiring", session, now, limits)

    assert preview_customer.reward_points_balance >= limits.gold_points_bonus_threshold
    assert customer.reward_points_balance == 0  # untouched
    assert intro_key == "simulate_points_expiring_intro"
