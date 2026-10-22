"""Versioning for rules/*.yaml: every change gets a timestamped snapshot
with who changed it and why. Git history already covers code-driven edits;
this covers edits made through the (Phase 7) no-code dashboard, where the
marketing person moving a slider has no git access.

Usage: python -m offerpilot.rules.versioning --by "Anjali" --summary "..."
"""
from datetime import datetime, timezone

from offerpilot.config import RULES_DIR
from offerpilot.db.models import RuleChangeLog
from offerpilot.db.session import SessionLocal, init_db

TRACKED_FILES = ["offer_catalogue.yaml", "limits.yaml", "fairness.yaml", "abuse.yaml"]


def snapshot(changed_by: str, summary: str, session=None) -> list[RuleChangeLog]:
    """Call this right after writing changes to rules/*.yaml."""
    own_session = session is None
    session = session or SessionLocal()
    try:
        init_db()
        now = datetime.now(timezone.utc)
        entries = []
        for filename in TRACKED_FILES:
            path = RULES_DIR / filename
            if not path.exists():
                continue
            entry = RuleChangeLog(
                changed_at=now, changed_by=changed_by, summary=summary,
                file=filename, content_snapshot=path.read_text(encoding="utf-8"),
            )
            session.add(entry)
            entries.append(entry)
        session.commit()
        return entries
    finally:
        if own_session:
            session.close()


def history(file: str | None = None, limit: int = 20, session=None) -> list[RuleChangeLog]:
    own_session = session is None
    session = session or SessionLocal()
    try:
        query = session.query(RuleChangeLog).order_by(RuleChangeLog.changed_at.desc())
        if file:
            query = query.filter(RuleChangeLog.file == file)
        return query.limit(limit).all()
    finally:
        if own_session:
            session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Snapshot current rules/*.yaml into the version log.")
    parser.add_argument("--by", required=True, help="Who is making this change")
    parser.add_argument("--summary", required=True, help="One-line summary of what changed and why")
    args = parser.parse_args()
    saved = snapshot(args.by, args.summary)
    print(f"Snapshotted {len(saved)} file(s) as a new version, by {args.by}: {args.summary}")
