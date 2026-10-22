"""Phase 1 event simulator: 12 months of realistic e-commerce behaviour per
customer (sessions, product views, cart activity, purchases, returns,
payment failures, reviews, support tickets), driven by each customer's
hidden persona. Then derives `total_spend`, `days_since_last_purchase`, and
`reward_points_balance` on the Customer row from what actually happened —
those fields are real feature-store inputs, not independently randomised.

Run generate_customers.py first. Usage: python -m offerpilot.data_gen.generate_events [--seed 42]
"""
import argparse
import random
from datetime import date, datetime, time, timedelta

import numpy as np

from offerpilot.data_gen.constants import (
    CATEGORY_RETURN_MULTIPLIER,
    COD_PROBABILITY_BY_TIER,
    DEFAULT_RETURN_MULTIPLIER,
    build_daily_multiplier,
    category_weights,
    default_window,
)
from offerpilot.data_gen.personas import PERSONA_PARAMS
from offerpilot.db.models import Customer, Event
from offerpilot.db.session import SessionLocal, init_db

CATEGORY_NAMES, CATEGORY_WEIGHTS = category_weights()

# Evening-peaked shopping hours, with a smaller lunchtime bump — not uniform.
_HOUR_RAW_WEIGHTS = [
    0.5, 0.3, 0.2, 0.2, 0.2, 0.3, 1.0, 2.0, 3.0, 3.5, 4.0, 4.5,
    5.5, 5.0, 4.5, 4.0, 4.5, 5.5, 7.0, 8.5, 9.0, 8.0, 5.0, 2.0,
]
HOUR_WEIGHTS = np.array(_HOUR_RAW_WEIGHTS) / sum(_HOUR_RAW_WEIGHTS)


def _temporal_shape(shape: str, n_days: int) -> np.ndarray:
    """Relative activity weight per eligible day — this is what encodes
    rising churn hazard (declining), long inactivity (sparse_tail), and
    short tenure (new_ramp) as actual behaviour, not just labels."""
    if shape == "declining":
        return np.linspace(1.0, 0.1, n_days)
    if shape == "sparse_tail":
        w = np.full(n_days, 0.02)
        active_days = max(1, n_days // 4)
        w[:active_days] = 1.0
        return w
    if shape == "new_ramp":
        return np.linspace(0.3, 1.0, n_days)
    return np.ones(n_days)  # "flat"


def _sample_hour() -> int:
    return int(np.random.choice(24, p=HOUR_WEIGHTS))


def _random_time_on(d: date) -> datetime:
    return datetime.combine(d, time(_sample_hour(), random.randint(0, 59)))


def _pick_category(preferred: str) -> str:
    if random.random() < 0.55:
        return preferred
    return random.choices(CATEGORY_NAMES, weights=CATEGORY_WEIGHTS, k=1)[0]


def _payment_method(city_tier: str) -> str:
    return "cod" if random.random() < COD_PROBABILITY_BY_TIER[city_tier] else "prepaid"


def _sample_rating(was_returned: bool) -> int:
    weights = [0.25, 0.2, 0.15, 0.2, 0.2] if was_returned else [0.03, 0.05, 0.12, 0.3, 0.5]
    return random.choices([1, 2, 3, 4, 5], weights=weights, k=1)[0]


def simulate_customer(
    customer: Customer, window_start: date, window_end: date, platform_mult: dict[date, float]
) -> tuple[list[Event], float, date | None]:
    params = PERSONA_PARAMS[customer.persona]
    eligible_start = max(customer.signup_date or window_start, window_start)
    if eligible_start > window_end:
        return [], 0.0, None

    n_days = (window_end - eligible_start).days + 1
    dates = [eligible_start + timedelta(days=i) for i in range(n_days)]
    platform = np.array([platform_mult[d] for d in dates])
    shape = _temporal_shape(params.temporal_shape, n_days)
    combined = platform * shape
    if combined.sum() <= 0:
        return [], 0.0, None
    p_days = combined / combined.sum()

    months_elapsed = n_days / 30.44
    expected_purchases = params.purchase_rate_per_month * months_elapsed * shape.mean()
    n_purchases = int(np.random.poisson(max(expected_purchases, 0.0)))

    preferred_category = random.choices(CATEGORY_NAMES, weights=CATEGORY_WEIGHTS, k=1)[0]

    events: list[Event] = []
    total_spend = 0.0
    last_purchase_date: date | None = None

    purchase_day_idxs = np.random.choice(n_days, size=n_purchases, p=p_days) if n_purchases else []
    for idx in purchase_day_idxs:
        d = dates[idx]
        ts = _random_time_on(d)
        category = _pick_category(preferred_category)
        amount = float(np.random.lognormal(mean=np.log(max(params.aov_mean, 50)), sigma=params.aov_sigma))
        amount = round(min(max(amount, 99.0), 25000.0), 2)
        payment_method = _payment_method(customer.city_tier)
        coupon_code = f"SAVE{random.randint(10, 40)}" if random.random() < params.coupon_use_rate else None

        events.append(Event(
            customer_id=customer.id, event_type="purchase", timestamp=ts,
            category=category, amount=amount, payment_method=payment_method, coupon_code=coupon_code,
        ))
        total_spend += amount
        if last_purchase_date is None or d > last_purchase_date:
            last_purchase_date = d

        return_mult = CATEGORY_RETURN_MULTIPLIER.get(category, DEFAULT_RETURN_MULTIPLIER)
        is_returned = random.random() < min(params.return_rate * return_mult, 0.85)
        if is_returned:
            return_ts = ts + timedelta(days=random.randint(2, 10))
            if return_ts.date() <= window_end:
                events.append(Event(
                    customer_id=customer.id, event_type="return", timestamp=return_ts,
                    category=category, amount=amount,
                ))
                total_spend -= amount  # net revenue

        if random.random() < 0.06:  # a failed attempt just before the (eventually successful) purchase
            fail_ts = ts - timedelta(minutes=random.randint(2, 40))
            if fail_ts.date() >= eligible_start:
                events.append(Event(
                    customer_id=customer.id, event_type="payment_failure", timestamp=fail_ts,
                    category=category, amount=amount, payment_method="prepaid",
                ))

        review_prob = 0.15 if is_returned else 0.3
        if random.random() < review_prob:
            review_ts = ts + timedelta(days=random.randint(3, 14))
            if review_ts.date() <= window_end:
                events.append(Event(
                    customer_id=customer.id, event_type="review", timestamp=review_ts,
                    category=category, rating=_sample_rating(is_returned),
                ))

        if is_returned and random.random() < 0.35:
            ticket_ts = ts + timedelta(days=random.randint(1, 6))
            if ticket_ts.date() <= window_end:
                events.append(Event(
                    customer_id=customer.id, event_type="support_ticket", timestamp=ticket_ts, category=category,
                ))

    # Funnel: sessions -> product views -> add-to-cart -> purchase | cart_abandon.
    baseline_sessions = 1 if shape.mean() > 0.05 else 0
    n_sessions = int(np.random.poisson(max(n_purchases * params.session_multiplier, baseline_sessions)))
    session_day_idxs = np.random.choice(n_days, size=n_sessions, p=p_days) if n_sessions else []
    for idx in session_day_idxs:
        d = dates[idx]
        events.append(Event(customer_id=customer.id, event_type="session", timestamp=_random_time_on(d)))

        for _ in range(np.random.randint(2, 7)):
            events.append(Event(
                customer_id=customer.id, event_type="product_view",
                timestamp=_random_time_on(d), category=_pick_category(preferred_category),
            ))

        if random.random() < 0.25:
            category = _pick_category(preferred_category)
            events.append(Event(customer_id=customer.id, event_type="add_to_cart", timestamp=_random_time_on(d), category=category))
            if random.random() < 0.65:  # most add-to-carts never convert
                events.append(Event(
                    customer_id=customer.id, event_type="cart_abandon",
                    timestamp=_random_time_on(d) + timedelta(hours=random.randint(1, 20)),
                    category=category,
                ))

    return events, total_spend, last_purchase_date


def main(seed: int, batch_size: int = 500) -> None:
    random.seed(seed)
    np.random.seed(seed)
    init_db()
    window_start, window_end = default_window()
    all_dates = [window_start + timedelta(days=i) for i in range((window_end - window_start).days + 1)]
    platform_mult = dict(zip(all_dates, build_daily_multiplier(all_dates)))

    session = SessionLocal()
    try:
        session.query(Event).delete()
        session.commit()

        customers = session.query(Customer).all()
        if not customers:
            raise SystemExit("No customers found — run generate_customers.py first.")

        total_events = 0
        batch: list[Event] = []
        for i, customer in enumerate(customers):
            events, total_spend, last_purchase_date = simulate_customer(customer, window_start, window_end, platform_mult)
            batch.extend(events)
            total_events += len(events)

            customer.total_spend = round(max(total_spend, 0.0), 2)
            customer.days_since_last_purchase = (
                (window_end - last_purchase_date).days if last_purchase_date else 9999
            )
            customer.reward_points_balance = min(int(customer.total_spend / 100 * random.uniform(0.6, 1.1)), 50000)

            if (i + 1) % batch_size == 0:
                session.bulk_save_objects(batch)
                session.commit()
                batch = []
                print(f"  ...{i + 1}/{len(customers)} customers simulated ({total_events} events so far)")

        session.bulk_save_objects(batch)
        session.commit()
        print(f"Generated {total_events} events for {len(customers)} customers.")
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    main(args.seed)
