"""Two-model (T-learner) uplift model — the project's key differentiator:
separately learns P(purchase | treated) and P(purchase | control) from the
simulated historical offer log, then uplift(x) = P_treated(x) - P_control(x).
This is what lets the agent avoid wasting a discount on a "sure-thing" who'd
buy anyway, and avoid bothering a "lost-cause" who won't buy regardless.

Trained ONLY on offerpilot.data_gen.generate_historical_offers' stored
feature columns — persona / latent_uplift_label are never seen by this
model; they're pulled back in afterwards purely to sanity-check it (see
`_report_against_hidden_labels`), never to fit it.

Usage: python -m offerpilot.features.uplift_model
"""
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import joblib

from offerpilot.config import DATA_DIR
from offerpilot.db.models import Customer, HistoricalOfferResponse
from offerpilot.db.session import SessionLocal

MODELS_DIR = DATA_DIR / "models"

NUMERIC_FEATURES = [
    "recency_days", "frequency", "monetary", "avg_order_value",
    "discount_sensitivity", "return_rate", "category_affinity_share", "tenure_days",
]
CATEGORICAL_FEATURES = ["city_tier", "loyalty_tier", "age_band", "device"]


def _build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    return Pipeline([
        ("preprocess", preprocessor),
        ("clf", GradientBoostingClassifier(random_state=42, n_estimators=150, max_depth=2, learning_rate=0.08)),
    ])


def load_training_data(session) -> pd.DataFrame:
    return pd.read_sql(session.query(HistoricalOfferResponse).statement, session.bind)


def train(session=None) -> dict:
    own_session = session is None
    session = session or SessionLocal()
    try:
        data = load_training_data(session)
        X = data[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
        y = data["responded"].astype(int)
        treated = data["treated"].astype(bool)

        X_train, X_test, y_train, y_test, treated_train, treated_test = train_test_split(
            X, y, treated, test_size=0.25, random_state=42, stratify=treated
        )

        model_t = _build_pipeline()
        model_t.fit(X_train[treated_train], y_train[treated_train])
        model_c = _build_pipeline()
        model_c.fit(X_train[~treated_train], y_train[~treated_train])

        auc_t = roc_auc_score(y_test[treated_test], model_t.predict_proba(X_test[treated_test])[:, 1])
        auc_c = roc_auc_score(y_test[~treated_test], model_c.predict_proba(X_test[~treated_test])[:, 1])

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(model_t, MODELS_DIR / "uplift_treated.joblib")
        joblib.dump(model_c, MODELS_DIR / "uplift_control.joblib")

        print(f"Uplift T-learner trained on {len(X_train)} historical offers "
              f"({int(treated_train.sum())} treated / {int((~treated_train).sum())} control).")
        print(f"Treated-arm test AUC: {auc_t:.3f} | Control-arm test AUC: {auc_c:.3f}")

        _report_against_hidden_labels(session, data, X, model_t, model_c)

        return {"auc_treated": auc_t, "auc_control": auc_c, "n_train": len(X_train), "n_test": len(X_test)}
    finally:
        if own_session:
            session.close()


def _report_against_hidden_labels(session, data: pd.DataFrame, X: pd.DataFrame, model_t, model_c) -> None:
    """Eval-only sanity check (result is printed, never fed back into the
    model): does predicted uplift actually rank persuadable highest and
    do-not-disturb/lost-cause lowest? Catches a broken simulation or a
    broken model before Phase 4 builds the agent on top of it."""
    customers = pd.read_sql(session.query(Customer.id, Customer.latent_uplift_label).statement, session.bind)
    uplift = model_t.predict_proba(X)[:, 1] - model_c.predict_proba(X)[:, 1]
    report = data[["customer_id"]].copy()
    report["predicted_uplift"] = uplift
    report = report.merge(customers, left_on="customer_id", right_on="id")
    print("\n[Eval only, never used by the model] mean predicted uplift by HIDDEN true label:")
    print(report.groupby("latent_uplift_label")["predicted_uplift"].mean().sort_values(ascending=False).round(4))


def load_models():
    return joblib.load(MODELS_DIR / "uplift_treated.joblib"), joblib.load(MODELS_DIR / "uplift_control.joblib")


_MODEL_CACHE: tuple | None = None


def load_models_cached() -> tuple | None:
    """Returns (model_t, model_c), or None if the models haven't been
    trained yet (python -m offerpilot.features.uplift_model) — callers on
    the hot path (the bot) should treat None as "uplift unavailable" rather
    than crashing the request."""
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        try:
            _MODEL_CACHE = load_models()
        except FileNotFoundError:
            return None
    return _MODEL_CACHE


def predict_uplift(model_t, model_c, features_df: pd.DataFrame) -> np.ndarray:
    X = features_df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    return model_t.predict_proba(X)[:, 1] - model_c.predict_proba(X)[:, 1]


def predict_uplift_for_one(customer, features: dict, model_t, model_c) -> float:
    """Single-customer convenience wrapper for the agent's estimate_uplift tool."""
    row = {col: features.get(col, 0) for col in NUMERIC_FEATURES}
    row["city_tier"] = customer.city_tier
    row["loyalty_tier"] = customer.loyalty_tier
    row["age_band"] = customer.age_band
    row["device"] = customer.device
    df = pd.DataFrame([row])
    return float(predict_uplift(model_t, model_c, df)[0])


if __name__ == "__main__":
    train()
