"""SQLAlchemy models. Schema is intentionally wider than the thin-slice generator
fills in — Phase 1's full generator will populate the rest without a migration.
"""
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    city_tier = Column(String, nullable=False)  # "metro" | "tier2" | "tier3"
    age_band = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    language = Column(String, nullable=False, default="en")  # en | hi | pa
    device = Column(String, nullable=True)
    signup_channel = Column(String, nullable=True)
    signup_date = Column(Date, nullable=True)
    loyalty_tier = Column(String, nullable=True)  # bronze | silver | gold
    reward_points_balance = Column(Integer, default=0)
    consent_opt_in = Column(Boolean, default=True)

    # feature-store-ish fields — set by generate_customers.py for the thin
    # slice, OVERWRITTEN from real simulated events once generate_events.py runs
    days_since_last_purchase = Column(Integer, default=9999)
    total_spend = Column(Float, default=0.0)

    # hidden ground truth — the engine/agent must never read these two columns
    persona = Column(String, nullable=True)
    latent_uplift_label = Column(String, nullable=True)

    # bound once a classmate runs /start against this synthetic customer
    telegram_chat_id = Column(Integer, nullable=True, unique=True)

    events = relationship("Event", back_populates="customer", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    # session | product_view | add_to_cart | cart_abandon | purchase | return
    # | payment_failure | review | support_ticket
    timestamp = Column(DateTime, nullable=False, index=True)

    category = Column(String, nullable=True)
    amount = Column(Float, nullable=True)
    payment_method = Column(String, nullable=True)  # "cod" | "prepaid"
    coupon_code = Column(String, nullable=True)
    rating = Column(Integer, nullable=True)
    related_event_id = Column(Integer, ForeignKey("events.id"), nullable=True)

    customer = relationship("Customer", back_populates="events")


class HistoricalOfferResponse(Base):
    """Simulated log of past (pre-agent) marketing offers: a 50/50 randomised
    treated/control exposure plus whether the customer purchased within the
    follow-up window. This is the ONLY place `offerpilot.data_gen` is allowed
    to let the hidden uplift label leak into generated data — it shapes how
    a treated customer responds, exactly as a real customer's unobservable
    persuadability would. Everything else here (the feature columns) is
    exactly what the uplift model is allowed to train on; persona and
    latent_uplift_label are intentionally NOT columns on this table.
    """
    __tablename__ = "historical_offer_responses"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    offer_timestamp = Column(DateTime, nullable=False)
    treated = Column(Boolean, nullable=False)
    responded = Column(Boolean, nullable=False)  # purchased within the follow-up window

    # features AS THEY WERE at offer_timestamp — not the customer's current state
    recency_days = Column(Integer, nullable=False)
    frequency = Column(Integer, nullable=False)
    monetary = Column(Float, nullable=False)
    avg_order_value = Column(Float, nullable=False)
    discount_sensitivity = Column(Float, nullable=False)
    return_rate = Column(Float, nullable=False)
    category_affinity_share = Column(Float, nullable=False)
    tenure_days = Column(Integer, nullable=False)
    city_tier = Column(String, nullable=False)
    loyalty_tier = Column(String, nullable=False)
    age_band = Column(String, nullable=True)
    device = Column(String, nullable=True)


class SentOffer(Base):
    """Every offer actually sent to a customer (rule-picked today, AI-picked
    from Phase 4 on). Backs frequency caps, cooldown, and budget pacing —
    those guardrails are meaningless without a real record of what already
    went out. Doubles as the start of the audit trail Phase 4 extends with
    agent reasoning and validator verdicts."""
    __tablename__ = "sent_offers"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    offer_type = Column(String, nullable=False)
    sent_at = Column(DateTime, nullable=False, index=True)
    cost_inr = Column(Float, nullable=False, default=0.0)


class RuleChangeLog(Base):
    """A snapshot of rules/*.yaml taken whenever they change — "versioned,
    every change logged with who changed what and when" from the brief.
    Git history covers code-driven changes; this covers changes made (or to
    be made, from Phase 7) through the no-code dashboard, where the person
    editing a slider has no git access."""
    __tablename__ = "rule_change_log"

    id = Column(Integer, primary_key=True)
    changed_at = Column(DateTime, nullable=False, index=True)
    changed_by = Column(String, nullable=False)
    summary = Column(String, nullable=False)
    file = Column(String, nullable=False)  # e.g. "limits.yaml"
    content_snapshot = Column(String, nullable=False)  # full file content at this point


class AuditLog(Base):
    """Every agent decision, win or lose: inputs, a short reasoning summary,
    what it chose, what the guardrail validator said, and the final message
    (if any was actually sent). This is what /why reads from in Phase 5, and
    what proves "guardrail-violation rate: 0 sent" for Phase 6."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, index=True)

    kill_switch_active = Column(Boolean, nullable=False, default=False)
    agent_reasoning_summary = Column(String, nullable=True)  # None when the kill switch bypassed the agent entirely
    proposed_offer_type = Column(String, nullable=True)
    proposed_message = Column(String, nullable=True)
    retries_used = Column(Integer, nullable=False, default=0)

    validator_verdict = Column(String, nullable=False)  # "pass" | "fail" | "fallback" | "bypassed"
    validator_reason = Column(String, nullable=True)

    final_offer_type = Column(String, nullable=False)  # what was ACTUALLY sent, after any fallback
    final_message = Column(String, nullable=False)
    used_fallback = Column(Boolean, nullable=False, default=False)
