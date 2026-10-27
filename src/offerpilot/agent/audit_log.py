from datetime import datetime

from offerpilot.db.models import AuditLog


def write_entry(
    session, customer_id: int, now: datetime, *,
    kill_switch_active: bool,
    agent_reasoning_summary: str | None,
    proposed_offer_type: str | None,
    proposed_message: str | None,
    retries_used: int,
    validator_verdict: str,
    validator_reason: str | None,
    final_offer_type: str,
    final_message: str,
    used_fallback: bool,
) -> AuditLog:
    entry = AuditLog(
        customer_id=customer_id, created_at=now,
        kill_switch_active=kill_switch_active,
        agent_reasoning_summary=agent_reasoning_summary,
        proposed_offer_type=proposed_offer_type,
        proposed_message=proposed_message,
        retries_used=retries_used,
        validator_verdict=validator_verdict,
        validator_reason=validator_reason,
        final_offer_type=final_offer_type,
        final_message=final_message,
        used_fallback=used_fallback,
    )
    session.add(entry)
    session.commit()
    return entry


def latest_for_customer(session, customer_id: int) -> AuditLog | None:
    return (
        session.query(AuditLog)
        .filter(AuditLog.customer_id == customer_id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
