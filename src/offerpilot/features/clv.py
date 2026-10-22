"""A simple, explainable CLV estimate: expected future spend = (observed
monthly purchase rate) x (avg order value) x (expected remaining lifetime),
where lifetime is derived from the churn model's probability.

Not a survival model — intentionally simple so a marketing reader can
sanity-check the formula, per the brief's usability bar.
"""
import numpy as np
import pandas as pd

MAX_CLV = 200_000.0
MIN_MONTHLY_CHURN = 0.02  # floor so lifetime never blows up to infinity


def estimate_clv(features_df: pd.DataFrame, churn_90d_prob: np.ndarray, horizon_days: int = 90) -> pd.Series:
    monthly_churn = 1 - (1 - churn_90d_prob) ** (30 / horizon_days)
    monthly_churn = np.clip(monthly_churn, MIN_MONTHLY_CHURN, 1.0)
    expected_lifetime_months = 1 / monthly_churn

    tenure_months = (features_df["tenure_days"] / 30).replace(0, np.nan)
    purchase_rate_per_month = (features_df["frequency"] / tenure_months).fillna(0.0)

    clv = features_df["avg_order_value"] * purchase_rate_per_month * expected_lifetime_months
    return clv.clip(upper=MAX_CLV)
