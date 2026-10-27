import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import offerpilot.agent.proactive_push as proactive_push
from offerpilot.db.models import Base


@pytest.fixture
def session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(proactive_push, "SessionLocal", Session)
    monkeypatch.setattr(proactive_push, "TELEGRAM_BOT_TOKEN", "123456789:fake-token-not-called")
    return Session


def test_push_with_no_connected_customers_sends_nothing(session_factory):
    summary = asyncio.run(proactive_push.push_to_eligible_customers())
    assert summary == {"sent": 0, "skipped": 0}
