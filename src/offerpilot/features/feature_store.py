"""Computes the feature-store columns (RFM + behavioural features) that the
rules engine, churn model, and uplift model are all allowed to see — never
persona or latent_uplift_label.

The core function, `compute_features_for`, takes a (customer_id, asof)
"key" per row and only uses events that happened at-or-before that row's
`asof` timestamp. That one mechanism serves two different callers:
  - the LIVE feature store (one row per customer, asof = now) used by the
    rules engine / agent, via `build_live_feature_store`.
  - historical point-in-time snapshots (one row per customer, asof = the
    timestamp of a past offer) used to train the churn and uplift models
    without leaking future information into their training features.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "recency_days", "frequency", "monetary", "avg_order_value",
    "discount_sensitivity", "return_rate", "category_affinity",
    "category_affinity_share", "last_cart_value", "tenure_days",
]


def compute_features_for(keys: pd.DataFrame, events: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """keys: DataFrame with columns [customer_id, asof] (one row per entity
    to score — asof may differ per row). Returns keys with FEATURE_COLUMNS
    appended, one output row per input key row."""
    keys = keys.reset_index(drop=True).copy()
    keys["_key"] = keys.index

    merged = events.merge(keys[["customer_id", "asof", "_key"]], on="customer_id", how="inner")
    merged = merged[merged["timestamp"] <= merged["asof"]]

    purchases = merged[merged.event_type == "purchase"]
    returns = merged[merged.event_type == "return"]
    carts = merged[merged.event_type.isin(["add_to_cart", "cart_abandon"])]

    out = keys.set_index("_key")[["customer_id", "asof"]].copy()

    freq = purchases.groupby("_key").size()
    out["frequency"] = freq.reindex(out.index, fill_value=0)

    gross = purchases.groupby("_key")["amount"].sum()
    out["monetary_gross"] = gross.reindex(out.index, fill_value=0.0)

    ret_amount = returns.groupby("_key")["amount"].sum()
    out["monetary"] = out["monetary_gross"] - ret_amount.reindex(out.index, fill_value=0.0)

    freq_or_nan = out["frequency"].replace(0, np.nan)
    out["avg_order_value"] = (out["monetary_gross"] / freq_or_nan).fillna(0.0).astype(float)

    ret_count = returns.groupby("_key").size()
    out["return_rate"] = (ret_count.reindex(out.index, fill_value=0) / freq_or_nan).fillna(0.0).astype(float)

    coupon_rate = purchases.groupby("_key")["coupon_code"].apply(lambda s: s.notna().mean())
    out["discount_sensitivity"] = coupon_rate.reindex(out.index, fill_value=0.0)

    last_purchase = (
        purchases.sort_values("timestamp", ascending=False)
        .drop_duplicates(subset="_key", keep="first")
        .set_index("_key")["timestamp"]
    )
    out["last_purchase_ts"] = last_purchase.reindex(out.index)
    recency = (out["asof"] - out["last_purchase_ts"]).dt.days
    out["recency_days"] = recency.fillna(9999).astype(int)

    cat_counts = purchases.groupby(["_key", "category"]).size().reset_index(name="n")
    cat_counts = cat_counts.sort_values("n", ascending=False).drop_duplicates(subset="_key", keep="first")
    cat_counts = cat_counts.set_index("_key")
    out["category_affinity"] = cat_counts["category"].reindex(out.index)
    out["category_affinity_share"] = (
        (cat_counts["n"].reindex(out.index) / freq_or_nan).fillna(0.0).astype(float)
    )

    last_cart = (
        carts.sort_values("timestamp", ascending=False)
        .drop_duplicates(subset="_key", keep="first")
        .set_index("_key")["amount"]
    )
    out["last_cart_value"] = last_cart.reindex(out.index, fill_value=0.0).fillna(0.0).astype(float)

    customers_idx = customers.set_index("id")
    signup = out["customer_id"].map(customers_idx["signup_date"])
    out["tenure_days"] = (pd.to_datetime(out["asof"]).dt.normalize() - pd.to_datetime(signup)).dt.days.clip(lower=0)

    out = out.drop(columns=["last_purchase_ts", "monetary_gross"])
    return out.reset_index(drop=True)


def build_live_feature_store(events: pd.DataFrame, customers: pd.DataFrame, asof: datetime) -> pd.DataFrame:
    """One row per customer, features as of `asof` (normally "now")."""
    keys = customers[["id"]].rename(columns={"id": "customer_id"})
    keys["asof"] = pd.Timestamp(asof)
    features = compute_features_for(keys, events, customers)
    return features.merge(
        customers[["id", "city_tier", "loyalty_tier", "age_band", "device", "consent_opt_in"]],
        left_on="customer_id", right_on="id",
    ).drop(columns=["id"])


def compute_features_for_customer(customer_id: int, asof: datetime, session) -> dict:
    """Single-customer feature lookup — queries only that customer's events
    instead of loading the whole platform, for use on the hot path (e.g. a
    Telegram /start handler)."""
    from offerpilot.db.models import Customer, Event  # local import avoids a cycle at module load

    customer = session.get(Customer, customer_id)
    events = pd.read_sql(
        session.query(Event).filter(Event.customer_id == customer_id).statement, session.bind
    )
    events["timestamp"] = pd.to_datetime(events["timestamp"])
    customers = pd.DataFrame([{"id": customer.id, "signup_date": pd.to_datetime(customer.signup_date)}])
    keys = pd.DataFrame({"customer_id": [customer_id], "asof": [pd.Timestamp(asof)]})

    out = compute_features_for(keys, events, customers)
    return out.iloc[0].to_dict()
