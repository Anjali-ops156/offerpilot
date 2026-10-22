"""Thin-slice customer generator: enough realism to exercise the rules engine
and the bot end-to-end. Phase 1 replaces this with the full generator
(events, Pareto spend, seasonality, persona-correlated behaviour).

Usage: python -m offerpilot.data_gen.generate_customers [--n 50] [--seed 42]
"""
import argparse
import random

from offerpilot.db.models import Customer
from offerpilot.db.session import SessionLocal, init_db

FIRST_NAMES = [
    "Simran", "Gurpreet", "Harpreet", "Amandeep", "Jaspreet", "Manpreet", "Navjot",
    "Rajveer", "Arshdeep", "Kiranjit", "Jasleen", "Baljeet", "Komal", "Rohit",
    "Priya", "Aarav", "Diya", "Karan", "Simranjeet", "Gagandeep",
]
LAST_NAMES = ["Singh", "Kaur", "Sharma", "Gill", "Brar", "Sidhu", "Sandhu", "Dhillon", "Mann", "Chahal"]

CITY_TIERS = {
    "Chandigarh": "metro",
    "Delhi NCR": "metro",
    "Ludhiana": "tier2",
    "Amritsar": "tier2",
    "Jalandhar": "tier2",
    "Patiala": "tier2",
    "Bathinda": "tier3",
    "Moga": "tier3",
    "Hoshiarpur": "tier3",
}

LANGUAGES = ["pa", "hi", "en"]
LANGUAGE_WEIGHTS = [0.4, 0.3, 0.3]

PERSONAS = [
    "Loyal Champion", "Deal Hunter", "At-Risk", "Dormant", "New Explorer",
    "Window Shopper", "Coupon Abuser", "High-Value Returner",
]
UPLIFT_LABELS = ["persuadable", "sure-thing", "lost-cause", "do-not-disturb"]
LOYALTY_TIERS = ["bronze", "silver", "gold"]


def make_customer(i: int) -> Customer:
    city = random.choice(list(CITY_TIERS))
    return Customer(
        name=f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
        city=city,
        city_tier=CITY_TIERS[city],
        age_band=random.choice(["18-24", "25-34", "35-44", "45-54", "55+"]),
        gender=random.choice(["F", "M", "other"]),
        language=random.choices(LANGUAGES, weights=LANGUAGE_WEIGHTS)[0],
        device=random.choice(["android", "ios", "web"]),
        signup_channel=random.choice(["organic", "referral", "ad", "influencer"]),
        loyalty_tier=random.choice(LOYALTY_TIERS),
        reward_points_balance=random.randint(0, 2000),
        consent_opt_in=random.random() > 0.05,
        days_since_last_purchase=random.randint(0, 120),
        total_spend=round(random.uniform(500, 60000), 2),
        persona=random.choice(PERSONAS),
        latent_uplift_label=random.choice(UPLIFT_LABELS),
    )


def main(n: int, seed: int) -> None:
    random.seed(seed)
    init_db()
    session = SessionLocal()
    try:
        session.query(Customer).delete()
        session.add_all(make_customer(i) for i in range(n))
        session.commit()
        print(f"Generated {n} synthetic customers.")
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    main(args.n, args.seed)
