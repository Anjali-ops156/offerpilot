from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import offerpilot.agent.agent as agent_module
from offerpilot.db.models import AuditLog, Base, Customer
from offerpilot.rules.engine import load_catalogue, load_limits


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def make_customer() -> Customer:
    return Customer(
        id=1, name="Test", city="Ludhiana", city_tier="tier2", language="en",
        loyalty_tier="bronze", reward_points_balance=0, consent_opt_in=True,
        days_since_last_purchase=1, total_spend=1000.0,
    )


def test_kill_switch_bypasses_the_agent_entirely(session, monkeypatch):
    monkeypatch.setattr(agent_module, "KILL_SWITCH", True)
    customer = make_customer()
    result = agent_module.run_agent_for_customer(
        customer, {}, load_catalogue(), load_limits(), session, datetime.now(),
    )
    assert result["used_ai"] is False

    entry = session.query(AuditLog).filter_by(customer_id=1).first()
    assert entry.kill_switch_active is True
    assert entry.validator_verdict == "bypassed"
    assert entry.used_fallback is True


def test_missing_api_key_bypasses_the_agent_and_still_responds(session, monkeypatch):
    monkeypatch.setattr(agent_module, "KILL_SWITCH", False)
    monkeypatch.setattr(agent_module, "ANTHROPIC_API_KEY", "")
    customer = make_customer()
    result = agent_module.run_agent_for_customer(
        customer, {}, load_catalogue(), load_limits(), session, datetime.now(),
    )
    assert result["used_ai"] is False
    assert result["message"]  # the classmate still gets SOME response, never a crash

    entry = session.query(AuditLog).filter_by(customer_id=1).first()
    assert entry.kill_switch_active is False
    assert "ANTHROPIC_API_KEY" in entry.validator_reason
