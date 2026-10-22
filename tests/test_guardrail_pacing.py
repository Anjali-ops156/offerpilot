from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from offerpilot.db.models import Base
from offerpilot.rules.engine import (
    can_send_now, check_budget, check_frequency, is_quiet_hours, load_limits, record_sent_offer,
)


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


def test_quiet_hours_wraps_past_midnight(limits):
    assert is_quiet_hours(datetime(2026, 1, 1, 23, 0), limits) is True
    assert is_quiet_hours(datetime(2026, 1, 1, 6, 0), limits) is True
    assert is_quiet_hours(datetime(2026, 1, 1, 14, 0), limits) is False


def test_fresh_customer_can_send_now(session, limits):
    now = datetime(2026, 1, 1, 14, 0)  # daytime, clear of quiet hours
    ok, reason = can_send_now(session, customer_id=1, limits=limits, proposed_cost_inr=50, now=now)
    assert ok is True, reason


def test_second_offer_same_day_blocked_by_frequency_cap(session, limits):
    now = datetime(2026, 1, 1, 14, 0)
    record_sent_offer(session, customer_id=1, offer_type="free_shipping", cost_inr=0, sent_at=now)

    ok, reason = check_frequency(session, customer_id=1, limits=limits, now=now)
    assert ok is False
    assert "max_offers_per_day" in reason


def test_cooldown_blocks_before_it_elapses(session, limits):
    now = datetime(2026, 1, 1, 14, 0)
    record_sent_offer(session, customer_id=2, offer_type="free_shipping", cost_inr=0, sent_at=now)

    later_same_day = now.replace(hour=20)
    ok, reason = check_frequency(session, customer_id=2, limits=limits, now=later_same_day)
    assert ok is False  # either the daily cap or the cooldown should catch this

    well_past_cooldown = now + timedelta(days=limits.cooldown_days_after_offer + 8)  # clear of the 7-day weekly cap too
    ok, reason = check_frequency(session, customer_id=2, limits=limits, now=well_past_cooldown)
    assert ok is True, reason


def test_daily_budget_blocks_once_exceeded(session, limits):
    now = datetime(2026, 1, 2, 14, 0)
    record_sent_offer(session, customer_id=3, offer_type="win_back_discount", cost_inr=limits.daily_budget_inr - 10, sent_at=now)

    ok, reason = check_budget(session, limits, proposed_cost_inr=20, now=now)
    assert ok is False
    assert "daily_budget_inr" in reason

    ok, reason = check_budget(session, limits, proposed_cost_inr=5, now=now)
    assert ok is True, reason
