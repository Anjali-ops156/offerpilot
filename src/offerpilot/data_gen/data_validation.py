"""Proves the synthetic data actually looks like a real platform's: Pareto
spend concentration, RFM spread, category long-tail, weekly/festival/salary
seasonality, a cohort retention curve, COD-by-tier, and category return
rates. Saves charts to data/validation/ and prints the headline numbers.

Usage: python -m offerpilot.data_gen.data_validation
"""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252, which can't print ₹

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from offerpilot.config import DATA_DIR
from offerpilot.db.models import Customer, Event
from offerpilot.db.session import SessionLocal

OUT_DIR = DATA_DIR / "validation"


def load_data():
    session = SessionLocal()
    try:
        customers = pd.read_sql(session.query(Customer).statement, session.bind)
        events = pd.read_sql(session.query(Event).statement, session.bind)
    finally:
        session.close()
    events["timestamp"] = pd.to_datetime(events["timestamp"])
    return customers, events


def spend_distribution(customers: pd.DataFrame) -> None:
    spend = customers["total_spend"].clip(lower=0).sort_values(ascending=False).reset_index(drop=True)
    n = len(spend)
    cum_customers = np.arange(1, n + 1) / n
    cum_revenue = spend.cumsum() / max(spend.sum(), 1e-9)

    top20_share = cum_revenue.iloc[int(n * 0.2) - 1] if n >= 5 else float("nan")
    print(f"[Pareto] top 20% of customers hold {top20_share:.1%} of total revenue (target: 70-80%)")

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(cum_customers * 100, cum_revenue * 100, label="Actual (sorted by spend)")
    ax.plot([0, 100], [0, 100], "--", color="gray", label="Perfect equality")
    ax.axvline(20, color="red", linestyle=":", label="Top 20% of customers")
    ax.set_xlabel("Cumulative % of customers (highest spend first)")
    ax.set_ylabel("Cumulative % of revenue")
    ax.set_title(f"Spend concentration (Lorenz curve) — top 20% = {top20_share:.0%} of revenue")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_DIR / "spend_pareto.png", dpi=120)
    plt.close(fig)


def rfm_spread(customers: pd.DataFrame) -> None:
    purchase_counts = customers.copy()
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))

    axes[0].hist(customers["days_since_last_purchase"].clip(upper=400), bins=40, color="#4C72B0")
    axes[0].set_title("Recency (days since last purchase, capped at 400)")
    axes[0].set_xlabel("Days")

    axes[1].hist(customers["total_spend"].clip(upper=customers["total_spend"].quantile(0.99)), bins=40, color="#55A868")
    axes[1].set_title("Monetary (total net spend, 99th pct capped)")
    axes[1].set_xlabel("INR")

    axes[2].hist(customers["reward_points_balance"], bins=40, color="#C44E52")
    axes[2].set_title("Reward points balance")
    axes[2].set_xlabel("Points")

    fig.suptitle("RFM-ish spread across the customer base")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "rfm_spread.png", dpi=120)
    plt.close(fig)
    print(f"[RFM] recency median={customers['days_since_last_purchase'].median():.0f}d, "
          f"spend median=₹{customers['total_spend'].median():.0f}, "
          f"spend p90=₹{customers['total_spend'].quantile(0.9):.0f}")


def category_long_tail(events: pd.DataFrame) -> None:
    purchases = events[events.event_type == "purchase"]
    counts = purchases["category"].value_counts()
    fig, ax = plt.subplots(figsize=(8, 5))
    counts.plot(kind="bar", ax=ax, color="#4C72B0")
    ax.set_yscale("log")
    ax.set_title("Category popularity (purchase count, log scale) — long tail")
    ax.set_ylabel("Purchases (log scale)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "category_long_tail.png", dpi=120)
    plt.close(fig)


def seasonality(events: pd.DataFrame) -> None:
    daily = events.groupby(events["timestamp"].dt.date).size()
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(daily.index, daily.values, color="#4C72B0", linewidth=0.8)
    ax.set_title("Daily event volume over the 12-month window (festival spikes visible)")
    ax.set_ylabel("Events")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(OUT_DIR / "seasonality_daily.png", dpi=120)
    plt.close(fig)

    dow = events.groupby(events["timestamp"].dt.day_name()).size()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dow = dow.reindex(order)
    fig, ax = plt.subplots(figsize=(7, 4))
    dow.plot(kind="bar", ax=ax, color="#55A868")
    ax.set_title("Weekly cycle: events by day of week (weekend bump)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "weekly_cycle.png", dpi=120)
    plt.close(fig)

    dom = events.groupby(events["timestamp"].dt.day).size()
    fig, ax = plt.subplots(figsize=(9, 4))
    dom.plot(kind="bar", ax=ax, color="#C44E52")
    ax.set_title("Events by day of month (salary-day bump at start/end)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "salary_day_bump.png", dpi=120)
    plt.close(fig)


def cohort_retention(customers: pd.DataFrame, events: pd.DataFrame) -> None:
    purchases = events[events.event_type == "purchase"].merge(
        customers[["id", "signup_date"]], left_on="customer_id", right_on="id"
    )
    purchases["signup_date"] = pd.to_datetime(purchases["signup_date"])
    purchases["cohort_month"] = purchases["signup_date"].dt.to_period("M")
    purchases["purchase_month_offset"] = (
        (purchases["timestamp"].dt.to_period("M") - purchases["cohort_month"]).apply(lambda x: x.n)
    )

    cohort_sizes = customers.copy()
    cohort_sizes["signup_date"] = pd.to_datetime(cohort_sizes["signup_date"])
    cohort_sizes["cohort_month"] = cohort_sizes["signup_date"].dt.to_period("M")
    sizes = cohort_sizes.groupby("cohort_month")["id"].nunique()

    retention = (
        purchases[purchases.purchase_month_offset >= 0]
        .groupby(["cohort_month", "purchase_month_offset"])["customer_id"]
        .nunique()
        .unstack(fill_value=0)
    )
    retention_pct = retention.divide(sizes, axis=0) * 100

    fig, ax = plt.subplots(figsize=(9, 5))
    avg_curve = retention_pct.mean(axis=0, skipna=True)
    avg_curve.plot(ax=ax, marker="o", color="#4C72B0")
    ax.set_title("Cohort retention curve (avg % of a signup cohort buying again, by month offset)")
    ax.set_xlabel("Months since signup")
    ax.set_ylabel("% of cohort with a purchase that month")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "cohort_retention.png", dpi=120)
    plt.close(fig)


def cod_by_tier(customers: pd.DataFrame, events: pd.DataFrame) -> None:
    purchases = events[events.event_type == "purchase"].merge(
        customers[["id", "city_tier"]], left_on="customer_id", right_on="id"
    )
    cod_share = purchases.groupby("city_tier")["payment_method"].apply(lambda s: (s == "cod").mean() * 100)
    cod_share = cod_share.reindex(["metro", "tier2", "tier3"])
    fig, ax = plt.subplots(figsize=(6, 4))
    cod_share.plot(kind="bar", ax=ax, color="#8172B2")
    ax.set_title("COD share by city tier (tier-3 should be highest)")
    ax.set_ylabel("% paid COD")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "cod_by_tier.png", dpi=120)
    plt.close(fig)
    print(f"[COD] by tier: {cod_share.round(1).to_dict()}")


def return_rate_by_category(events: pd.DataFrame) -> None:
    purchases = events[events.event_type == "purchase"].groupby("category").size()
    returns = events[events.event_type == "return"].groupby("category").size()
    rate = (returns / purchases * 100).reindex(purchases.index).fillna(0).sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(8, 5))
    rate.plot(kind="bar", ax=ax, color="#DD8452")
    ax.set_title("Return rate by category (Fashion should lead)")
    ax.set_ylabel("% of purchases returned")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "return_rate_by_category.png", dpi=120)
    plt.close(fig)
    print(f"[Returns] by category (top 3): {rate.head(3).round(1).to_dict()}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    customers, events = load_data()
    print(f"Loaded {len(customers)} customers and {len(events)} events.\n")

    spend_distribution(customers)
    rfm_spread(customers)
    category_long_tail(events)
    seasonality(events)
    cohort_retention(customers, events)
    cod_by_tier(customers, events)
    return_rate_by_category(events)

    print(f"\nCharts written to {OUT_DIR}")


if __name__ == "__main__":
    main()
