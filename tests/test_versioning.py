import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from offerpilot.db.models import Base
from offerpilot.rules.versioning import history, snapshot


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_snapshot_records_every_tracked_file(session):
    entries = snapshot("Anjali", "baseline", session=session)
    assert len(entries) == 4  # offer_catalogue, limits, fairness, abuse
    assert all(e.changed_by == "Anjali" for e in entries)
    assert all(e.content_snapshot for e in entries)


def test_history_returns_most_recent_first(session):
    snapshot("Anjali", "first change", session=session)
    snapshot("Anjali", "second change", session=session)

    recent = history(file="limits.yaml", session=session)
    assert len(recent) == 2
    assert recent[0].summary == "second change"
