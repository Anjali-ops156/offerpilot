"""Phase 1 full customer generator: realistic profiles with persona-correlated
loyalty tier, language, and signup recency. `total_spend`,
`days_since_last_purchase`, and `reward_points_balance` are placeholders here
— run generate_events.py afterwards to derive them from simulated behaviour.

Usage: python -m offerpilot.data_gen.generate_customers [--n 5000] [--seed 42]
"""
import argparse
import random
from datetime import timedelta

from offerpilot.data_gen.constants import CITY_TIERS, default_window
from offerpilot.data_gen.personas import assign_loyalty_tier, assign_persona, assign_uplift_label
from offerpilot.db.models import Customer
from offerpilot.db.session import SessionLocal, init_db

FIRST_NAMES = [
    "Simran", "Gurpreet", "Harpreet", "Amandeep", "Jaspreet", "Manpreet", "Navjot",
    "Rajveer", "Arshdeep", "Kiranjit", "Jasleen", "Baljeet", "Komal", "Rohit",
    "Priya", "Aarav", "Diya", "Karan", "Simranjeet", "Gagandeep", "Ramanpreet",
    "Harman", "Taranjit", "Jasmine", "Sukhpreet", "Inderjit", "Navdeep", "Anmol",
]
LAST_NAMES = ["Singh", "Kaur", "Sharma", "Gill", "Brar", "Sidhu", "Sandhu", "Dhillon", "Mann", "Chahal"]

# Metro skews more English; tier-3 skews more Punjabi — small, realistic tilt.
LANGUAGE_WEIGHTS_BY_TIER = {
    "metro": {"en": 0.5, "hi": 0.3, "pa": 0.2},
    "tier2": {"en": 0.25, "hi": 0.3, "pa": 0.45},
    "tier3": {"en": 0.15, "hi": 0.25, "pa": 0.6},
}


def _weighted(d: dict[str, float]) -> str:
    return random.choices(list(d), weights=list(d.values()), k=1)[0]


def _signup_date(persona: str, window_start, window_end):
    """New Explorers signed up recently (within the last ~90 days of the
    window); everyone else has tenure spread over the last ~3 years, skewed
    recent via an exponential draw."""
    if persona == "New Explorer":
        days_ago = random.randint(0, 90)
        return window_end - timedelta(days=days_ago)

    days_ago = min(int(random.expovariate(1 / 240)), 365 * 3)
    return window_end - timedelta(days=days_ago)


def make_customer(window_start, window_end) -> Customer:
    city = random.choice(list(CITY_TIERS))
    city_tier = CITY_TIERS[city]
    persona = assign_persona()

    return Customer(
        name=f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
        city=city,
        city_tier=city_tier,
        age_band=random.choice(["18-24", "25-34", "35-44", "45-54", "55+"]),
        gender=random.choice(["F", "M", "other"]),
        language=_weighted(LANGUAGE_WEIGHTS_BY_TIER[city_tier]),
        device=random.choices(["android", "ios", "web"], weights=[0.65, 0.2, 0.15])[0],
        signup_channel=random.choice(["organic", "referral", "ad", "influencer"]),
        signup_date=_signup_date(persona, window_start, window_end),
        loyalty_tier=assign_loyalty_tier(persona),
        reward_points_balance=0,  # derived in generate_events.py
        consent_opt_in=random.random() > 0.05,
        days_since_last_purchase=9999,  # derived in generate_events.py
        total_spend=0.0,  # derived in generate_events.py
        persona=persona,
        latent_uplift_label=assign_uplift_label(persona),
    )


def main(n: int, seed: int) -> None:
    random.seed(seed)
    window_start, window_end = default_window()
    init_db()
    session = SessionLocal()
    try:
        session.query(Customer).delete()
        session.add_all(make_customer(window_start, window_end) for _ in range(n))
        session.commit()
        print(f"Generated {n} synthetic customers (window {window_start} -> {window_end}).")
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    main(args.n, args.seed)
