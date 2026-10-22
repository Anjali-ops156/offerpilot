import pandas as pd

from offerpilot.features.feature_store import compute_features_for


def _events(rows):
    df = pd.DataFrame(rows, columns=["customer_id", "event_type", "timestamp", "category", "amount", "coupon_code"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def test_features_for_customer_with_purchases_and_a_return():
    events = _events([
        (1, "purchase", "2026-01-01", "Fashion", 1000.0, "SAVE10"),
        (1, "purchase", "2026-01-10", "Fashion", 500.0, None),
        (1, "return", "2026-01-12", "Fashion", 500.0, None),
        (1, "add_to_cart", "2026-01-15", "Electronics", 2000.0, None),
    ])
    customers = pd.DataFrame({"id": [1], "signup_date": pd.to_datetime(["2025-12-01"])})
    keys = pd.DataFrame({"customer_id": [1], "asof": pd.to_datetime(["2026-01-20"])})

    out = compute_features_for(keys, events, customers).iloc[0]

    assert out["frequency"] == 2
    assert out["monetary"] == 1000.0  # 1000 + 500 - 500 return
    assert out["avg_order_value"] == 750.0  # gross 1500 / 2 purchases
    assert out["return_rate"] == 0.5
    assert out["discount_sensitivity"] == 0.5  # 1 of 2 purchases used a coupon
    assert out["recency_days"] == 10  # Jan 20 - Jan 10
    assert out["category_affinity"] == "Fashion"
    assert out["category_affinity_share"] == 1.0
    assert out["last_cart_value"] == 2000.0
    assert out["tenure_days"] == 50  # Jan 20 - Dec 1


def test_customer_with_no_events_gets_safe_defaults():
    events = _events([])
    customers = pd.DataFrame({"id": [2], "signup_date": pd.to_datetime(["2026-01-01"])})
    keys = pd.DataFrame({"customer_id": [2], "asof": pd.to_datetime(["2026-01-15"])})

    out = compute_features_for(keys, events, customers).iloc[0]

    assert out["frequency"] == 0
    assert out["monetary"] == 0.0
    assert out["avg_order_value"] == 0.0
    assert out["return_rate"] == 0.0
    assert out["recency_days"] == 9999
    assert pd.isna(out["category_affinity"])
    assert out["last_cart_value"] == 0.0


def test_events_after_asof_are_ignored_no_future_leakage():
    events = _events([
        (3, "purchase", "2026-01-01", "Fashion", 1000.0, None),
        (3, "purchase", "2026-02-01", "Fashion", 9000.0, None),  # after asof — must not count
    ])
    customers = pd.DataFrame({"id": [3], "signup_date": pd.to_datetime(["2025-12-01"])})
    keys = pd.DataFrame({"customer_id": [3], "asof": pd.to_datetime(["2026-01-15"])})

    out = compute_features_for(keys, events, customers).iloc[0]

    assert out["frequency"] == 1
    assert out["monetary"] == 1000.0
