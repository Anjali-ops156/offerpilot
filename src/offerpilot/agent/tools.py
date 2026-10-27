"""Tool definitions the Claude agent calls, and the dispatcher that executes
them. Every tool is scoped to the ONE customer the agent was invoked for —
customer_id is never a tool parameter, so the model has no way to ask about
anyone else's account even if it tried.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from offerpilot.agent.guardrail_validator import validate_submission
from offerpilot.db.models import Customer, Event
from offerpilot.features.next_best_action import offer_cost_inr
from offerpilot.features.next_best_action import simulate_margin as _simulate_margin
from offerpilot.rules.engine import check_budget as _check_budget
from offerpilot.rules.engine import get_eligible_offers
from offerpilot.rules.schema import Limits, Offer, OfferCatalogue

LABEL_FIELD = {"en": "label_en", "hi": "label_hi", "pa": "label_pa"}
DEFAULT_ORDER_VALUE_INR = 1000.0


@dataclass
class AgentContext:
    session: object
    customer: Customer
    features: dict
    catalogue: OfferCatalogue
    limits: Limits
    now: datetime
    language: str
    uplift_score: float | None  # None if the uplift model isn't trained yet
    submission: dict | None = None  # set once a submit_offer call is ACCEPTED
    retries_used: int = 0
    last_rejection_reason: str | None = None


def _label(offer: Offer, language: str) -> str:
    field = LABEL_FIELD.get(language, "label_en")
    return getattr(offer, field).format(pct=int(offer.value))


TOOLS = [
    {
        "name": "get_customer_profile",
        "description": "Returns this customer's own-account profile: city tier, age band, language, "
                        "device, loyalty tier, reward points balance, consent status, tenure, and "
                        "RFM-style behaviour. Never includes any other customer's data.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_recent_events",
        "description": "Returns this customer's most recent activity (purchases, returns, cart "
                        "activity, sessions) over the given number of days, most recent first.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "Lookback window in days", "default": 30}},
        },
    },
    {
        "name": "get_eligible_offers",
        "description": "Returns the offers this customer is ALLOWED to receive right now, after "
                        "consent, abuse-protection, value-cap, and fairness filtering. You may only "
                        "choose an offer type from this list — anything else will be rejected.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "estimate_uplift",
        "description": "Returns this customer's estimated purchase-probability UPLIFT from receiving "
                        "an offer vs. none — a signed number. Near zero or negative means an offer "
                        "likely won't change their behaviour (don't spend a discount on them); a "
                        "clearly positive number means an offer is likely to persuade them.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "simulate_margin",
        "description": "For a given offer type, returns the expected gross margin, the offer's cost, "
                        "net margin, and net margin as a percent of order value.",
        "input_schema": {
            "type": "object", "properties": {"offer_type": {"type": "string"}}, "required": ["offer_type"],
        },
    },
    {
        "name": "check_budget",
        "description": "Checks whether sending a given offer right now would exceed the daily or "
                        "campaign budget.",
        "input_schema": {
            "type": "object", "properties": {"offer_type": {"type": "string"}}, "required": ["offer_type"],
        },
    },
    {
        "name": "draft_message",
        "description": "Returns the AUTHORITATIVE base sentence for an offer, in the customer's "
                        "preferred language, with the real discount value already filled in. You "
                        "MUST include this exact number/value — you may add a short greeting and "
                        "relevant context (festival, category) around it, but never invent a "
                        "different discount amount.",
        "input_schema": {
            "type": "object", "properties": {"offer_type": {"type": "string"}}, "required": ["offer_type"],
        },
    },
    {
        "name": "submit_offer",
        "description": "Submits your final decision: the offer type to send ('no_offer' is a valid, "
                        "deliberate choice to send nothing) and the exact message to send. Checked by "
                        "a guardrail validator — if rejected you'll get a reason and may try again.",
        "input_schema": {
            "type": "object",
            "properties": {
                "offer_type": {"type": "string"},
                "message": {"type": "string"},
                "reasoning_summary": {
                    "type": "string",
                    "description": "One or two plain-language sentences on WHY you chose this — may "
                                    "be shown to the customer if they ask why. Never mention internal "
                                    "scores, model names, or the words persona/uplift/churn.",
                },
            },
            "required": ["offer_type", "message", "reasoning_summary"],
        },
    },
]


def _profile(ctx: AgentContext) -> dict:
    c = ctx.customer
    f = ctx.features
    return {
        "city_tier": c.city_tier,
        "age_band": c.age_band,
        "language": c.language,
        "device": c.device,
        "loyalty_tier": c.loyalty_tier,
        "reward_points_balance": c.reward_points_balance,
        "consent_opt_in": c.consent_opt_in,
        "tenure_days": f.get("tenure_days"),
        "recency_days": f.get("recency_days"),
        "frequency": f.get("frequency"),
        "monetary_inr": f.get("monetary"),
        "avg_order_value_inr": f.get("avg_order_value"),
        "favourite_category": f.get("category_affinity"),
        "discount_sensitivity": f.get("discount_sensitivity"),
        "return_rate": f.get("return_rate"),
    }


def _recent_events(ctx: AgentContext, days: int) -> list[dict]:
    cutoff = ctx.now - timedelta(days=days)
    rows = (
        ctx.session.query(Event)
        .filter(Event.customer_id == ctx.customer.id, Event.timestamp >= cutoff, Event.timestamp <= ctx.now)
        .order_by(Event.timestamp.desc())
        .limit(25)
        .all()
    )
    return [
        {"event_type": r.event_type, "timestamp": r.timestamp.isoformat(), "category": r.category, "amount": r.amount}
        for r in rows
    ]


def _eligible_offers_payload(ctx: AgentContext) -> list[dict]:
    offers = get_eligible_offers(ctx.customer, ctx.features, ctx.catalogue, ctx.limits)
    return [{"type": o.type, "kind": o.kind, "value": o.value, "label": _label(o, ctx.language)} for o in offers]


def dispatch_tool(name: str, tool_input: dict, ctx: AgentContext) -> dict:
    if name == "get_customer_profile":
        return _profile(ctx)

    if name == "get_recent_events":
        return {"events": _recent_events(ctx, tool_input.get("days", 30))}

    if name == "get_eligible_offers":
        return {"offers": _eligible_offers_payload(ctx)}

    if name == "estimate_uplift":
        if ctx.uplift_score is None:
            return {"uplift": None, "note": "uplift model unavailable — use judgement from profile/events instead"}
        return {
            "uplift": round(ctx.uplift_score, 4),
            "note": "estimated lift in purchase probability from receiving SOME offer vs none; "
                    "not specific to one offer type",
        }

    if name == "simulate_margin":
        offer = ctx.catalogue.get(tool_input["offer_type"])
        sim = _simulate_margin(ctx.features.get("avg_order_value") or DEFAULT_ORDER_VALUE_INR, offer, ctx.limits)
        return {
            "gross_margin_inr": sim.gross_margin_inr, "offer_cost_inr": sim.offer_cost_inr,
            "net_margin_inr": sim.net_margin_inr, "net_margin_pct": sim.net_margin_pct,
        }

    if name == "check_budget":
        offer = ctx.catalogue.get(tool_input["offer_type"])
        cost = offer_cost_inr(ctx.features.get("avg_order_value") or DEFAULT_ORDER_VALUE_INR, offer, ctx.limits)
        ok, reason = _check_budget(ctx.session, ctx.limits, cost, ctx.now)
        return {"ok": ok, "reason": reason}

    if name == "draft_message":
        eligible = {o.type: o for o in get_eligible_offers(ctx.customer, ctx.features, ctx.catalogue, ctx.limits)}
        offer = eligible.get(tool_input["offer_type"]) or ctx.catalogue.get(tool_input["offer_type"])
        return {"base_sentence": _label(offer, ctx.language)}

    if name == "submit_offer":
        ok, reason, offer = validate_submission(
            ctx.customer, ctx.features, tool_input["offer_type"], tool_input["message"],
            ctx.catalogue, ctx.limits, ctx.session, ctx.now,
        )
        if ok:
            ctx.submission = {
                "offer_type": tool_input["offer_type"],
                "message": tool_input["message"],
                "reasoning_summary": tool_input.get("reasoning_summary", ""),
                "offer": offer,
            }
            return {"accepted": True}
        ctx.retries_used += 1
        ctx.last_rejection_reason = reason
        return {"accepted": False, "reason": reason}

    raise ValueError(f"Unknown tool: {name}")
