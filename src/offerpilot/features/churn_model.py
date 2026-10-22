"""Churn-risk model: predicts the probability a customer makes NO purchase
in the CHURN_HORIZON_DAYS after a cutoff date, trained using only features
known as-of that cutoff — so there's no future leakage into training.

Usage: python -m offerpilot.features.churn_model
"""
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import joblib

from offerpilot.config import DATA_DIR
from offerpilot.data_gen.constants import default_window
from offerpilot.db.models import Customer, Event
from offerpilot.db.session import SessionLocal
from offerpilot.features.feature_store import compute_features_for

MODELS_DIR = DATA_DIR / "models"
CHURN_HORIZON_DAYS = 90

NUMERIC_FEATURES = [
    "recency_days", "frequency", "monetary", "avg_order_value",
    "discount_sensitivity", "return_rate", "category_affinity_share",
    "last_cart_value", "tenure_days",
]
CATEGORICAL_FEATURES = ["city_tier", "loyalty_tier", "age_band", "device"]


def _build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    return Pipeline([
        ("preprocess", preprocessor),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])


def build_training_set(session) -> pd.DataFrame:
    """One row per customer with >=14 days of pre-cutoff history: features
    as of `cutoff`, label = 1 if they did NOT purchase again within
    CHURN_HORIZON_DAYS after it."""
    window_start, window_end = default_window()
    cutoff = pd.Timestamp(window_end) - pd.Timedelta(days=CHURN_HORIZON_DAYS)

    customers = pd.read_sql(session.query(Customer).statement, session.bind)
    events = pd.read_sql(session.query(Event).statement, session.bind)
    events["timestamp"] = pd.to_datetime(events["timestamp"])
    customers["signup_date"] = pd.to_datetime(customers["signup_date"])

    eligible = customers[customers["signup_date"] <= cutoff - pd.Timedelta(days=14)].copy()
    keys = eligible[["id"]].rename(columns={"id": "customer_id"})
    keys["asof"] = cutoff

    features = compute_features_for(keys, events, customers)
    features = features.merge(
        customers[["id", "city_tier", "loyalty_tier", "age_band", "device"]],
        left_on="customer_id", right_on="id",
    ).drop(columns=["id"])

    future_purchases = events[
        (events.event_type == "purchase") & (events.timestamp > cutoff) & (events.timestamp <= pd.Timestamp(window_end))
    ]
    purchased_after = set(future_purchases.customer_id.unique())
    features["churned"] = (~features["customer_id"].isin(purchased_after)).astype(int)
    return features


def train(session=None) -> dict:
    own_session = session is None
    session = session or SessionLocal()
    try:
        data = build_training_set(session)
        X = data[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
        y = data["churned"]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        pipeline = _build_pipeline()
        pipeline.fit(X_train, y_train)
        test_auc = roc_auc_score(y_test, pipeline.predict_proba(X_test)[:, 1])

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipeline, MODELS_DIR / "churn_model.joblib")

        print(f"Churn model trained on {len(X_train)} customers, tested on {len(X_test)}.")
        print(f"Churn base rate: {y.mean():.1%} | Test AUC: {test_auc:.3f}")
        return {"test_auc": test_auc, "n_train": len(X_train), "n_test": len(X_test), "base_rate": float(y.mean())}
    finally:
        if own_session:
            session.close()


def load_model():
    return joblib.load(MODELS_DIR / "churn_model.joblib")


def predict_churn_risk(model, features_df: pd.DataFrame) -> np.ndarray:
    X = features_df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    return model.predict_proba(X)[:, 1]


if __name__ == "__main__":
    train()
