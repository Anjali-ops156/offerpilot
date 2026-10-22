"""Simulates a year of PAST marketing offers — a 50/50 randomised
treated/control exposure per eligible customer, with a 14-day follow-up
outcome. This is the only place in the codebase where the hidden
`latent_uplift_label` is allowed to influence anything outside the
personas/events simulation: here, it shapes how a treated customer responds,
exactly as a real (unobservable) persuadability would have shaped a real
historical campaign's results.

The uplift model trains on this table using ONLY the stored feature columns
(recency, frequency, monetary, ...) — persona and latent_uplift_label are
not columns on `historical_offer_responses` and never touch model training.

Run after generate_events.py. Usage:
    python -m offerpilot.data_gen.generate_historical_offers [--seed 42]
"""
import argparse
import random
from datetime import timedelta

import numpy as np
import pandas as pd

from offerpilot.data_gen.constants import default_window
from offerpilot.data_gen.personas import PERSONA_PARAMS
from offerpilot.db.models import Customer, Event, HistoricalOfferResponse
from offerpilot.db.session import SessionLocal, init_db
from offerpilot.features.feature_store import compute_features_for

FOLLOWUP_DAYS = 14
MIN_HISTORY_DAYS = 14
TREATMENT_SHARE = 0.9  # share of customers who have ANY historical offer on record


def _organic_14d_prob(persona: str) -> float:
    monthly_rate = PERSONA_PARAMS[persona].purchase_rate_per_month
    return 1 - np.exp(-monthly_rate * FOLLOWUP_DAYS / 30.44)


def _response_probability(persona: str, uplift_label: str, treated: bool) -> float:
    base = _organic_14d_prob(persona)
    if uplift_label == "sure-thing":
        prob = base
    elif uplift_label == "lost-cause":
        prob = base * 0.25
    elif uplift_label == "persuadable":
        prob = base * 0.45 + (0.32 if treated else 0.0)
    else:  # do-not-disturb
        prob = base * 0.6 - (0.14 if treated else 0.0)

    prob *= random.uniform(0.92, 1.08)
    return float(np.clip(prob, 0.01, 0.97))


def _pick_offer_timestamp(signup_date, window_start, window_end):
    earliest = max(signup_date, window_start) + timedelta(days=MIN_HISTORY_DAYS)
    latest = window_end - timedelta(days=FOLLOWUP_DAYS)
    if earliest >= latest:
        return None
    days_span = (latest - earliest).days
    offer_date = earliest + timedelta(days=random.randint(0, days_span))
    return pd.Timestamp(offer_date) + pd.Timedelta(hours=random.randint(8, 21))


def main(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    init_db()
    window_start, window_end = default_window()

    session = SessionLocal()
    try:
        session.query(HistoricalOfferResponse).delete()
        session.commit()

        customers = pd.read_sql(session.query(Customer).statement, session.bind)
        events = pd.read_sql(session.query(Event).statement, session.bind)
        events["timestamp"] = pd.to_datetime(events["timestamp"])
        customers["signup_date"] = pd.to_datetime(customers["signup_date"])

        eligible = customers.sample(frac=TREATMENT_SHARE, random_state=seed).copy()
        keys = []
        for _, row in eligible.iterrows():
            ts = _pick_offer_timestamp(row["signup_date"], pd.Timestamp(window_start), pd.Timestamp(window_end))
            if ts is not None:
                keys.append({"customer_id": row["id"], "asof": ts})
        keys_df = pd.DataFrame(keys)
        print(f"{len(keys_df)}/{len(customers)} customers eligible for a historical offer.")

        features = compute_features_for(keys_df, events, customers)
        features = features.merge(
            customers[["id", "city_tier", "loyalty_tier", "age_band", "device", "persona", "latent_uplift_label", "signup_date"]],
            left_on="customer_id", right_on="id",
        )

        rows = []
        for _, f in features.iterrows():
            treated = random.random() < 0.5
            prob = _response_probability(f["persona"], f["latent_uplift_label"], treated)
            responded = random.random() < prob
            rows.append(HistoricalOfferResponse(
                customer_id=int(f["customer_id"]),
                offer_timestamp=f["asof"].to_pydatetime(),
                treated=treated,
                responded=responded,
                recency_days=int(f["recency_days"]),
                frequency=int(f["frequency"]),
                monetary=float(f["monetary"]),
                avg_order_value=float(f["avg_order_value"]),
                discount_sensitivity=float(f["discount_sensitivity"]),
                return_rate=float(f["return_rate"]),
                category_affinity_share=float(f["category_affinity_share"]),
                tenure_days=int(f["tenure_days"]),
                city_tier=f["city_tier"],
                loyalty_tier=f["loyalty_tier"],
                age_band=f["age_band"],
                device=f["device"],
            ))

        session.bulk_save_objects(rows)
        session.commit()
        response_rate = sum(r.responded for r in rows) / max(len(rows), 1)
        treated_rate = sum(r.responded for r in rows if r.treated) / max(sum(r.treated for r in rows), 1)
        control_rate = sum(r.responded for r in rows if not r.treated) / max(sum(not r.treated for r in rows), 1)
        print(f"Generated {len(rows)} historical offer rows. "
              f"Overall response {response_rate:.1%}, treated {treated_rate:.1%}, control {control_rate:.1%}.")
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    main(args.seed)
