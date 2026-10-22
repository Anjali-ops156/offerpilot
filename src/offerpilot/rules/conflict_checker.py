"""Validates rules/*.yaml for internal contradictions or settings that make
an offer impossible to ever send — catches a marketing editor's mistake
before it reaches production, not just at request time.

Usage: python -m offerpilot.rules.conflict_checker
Exit code 1 if any conflicts are found (safe to wire into CI / pre-merge).
"""
from offerpilot.rules.engine import load_catalogue, load_limits
from offerpilot.rules.schema import Limits, OfferCatalogue

TIER_ORDER = ["bronze", "silver", "gold"]
CORE_OFFER_TYPES = {"win_back_discount", "welcome_offer", "free_shipping", "bonus_points", "no_offer"}


def check_conflicts(catalogue: OfferCatalogue, limits: Limits) -> list[str]:
    warnings: list[str] = []

    seen = set()
    for offer in catalogue.offers:
        if offer.type in seen:
            warnings.append(f"Duplicate offer type '{offer.type}' in offer_catalogue.yaml.")
        seen.add(offer.type)

    for offer in catalogue.offers:
        if offer.kind == "percent_off" and offer.value > limits.max_discount_pct:
            warnings.append(
                f"Offer '{offer.type}' is {offer.value}% off, which exceeds max_discount_pct "
                f"({limits.max_discount_pct}%) — it will always be rejected by validate_offer()."
            )
        if offer.kind == "flat_off_inr" and offer.value > limits.max_offer_value_inr:
            warnings.append(
                f"Offer '{offer.type}' costs Rs {offer.value}, which exceeds max_offer_value_inr "
                f"(Rs {limits.max_offer_value_inr}) — it will always be rejected."
            )
        if offer.kind == "bonus_points":
            cost = offer.value * limits.points_to_inr
            if cost > limits.max_offer_value_inr:
                warnings.append(
                    f"Offer '{offer.type}' costs Rs {cost:.0f} in points liability, which exceeds "
                    f"max_offer_value_inr (Rs {limits.max_offer_value_inr})."
                )

    for category, cap in limits.category_discount_caps.items():
        if cap > limits.max_discount_pct:
            warnings.append(
                f"category_discount_caps['{category}'] = {cap}% is above max_discount_pct "
                f"({limits.max_discount_pct}%) — the global cap already applies, so this has no effect."
            )

    tier_pcts = limits.win_back_discount_pct_by_tier
    for lower, higher in zip(TIER_ORDER, TIER_ORDER[1:]):
        if lower in tier_pcts and higher in tier_pcts and tier_pcts[higher] < tier_pcts[lower]:
            warnings.append(
                f"win_back_discount_pct_by_tier: {higher} ({tier_pcts[higher]}%) is LOWER than "
                f"{lower} ({tier_pcts[lower]}%) — violates 'loyal customers never get a worse deal'."
            )
    for tier, pct in tier_pcts.items():
        if pct > limits.max_discount_pct:
            warnings.append(
                f"win_back_discount_pct_by_tier['{tier}'] = {pct}% exceeds max_discount_pct "
                f"({limits.max_discount_pct}%) — it will always be rejected."
            )

    worst_case_net_margin_pct = limits.gross_margin_pct - limits.max_discount_pct
    if worst_case_net_margin_pct < limits.min_margin_floor_pct:
        warnings.append(
            f"At max_discount_pct ({limits.max_discount_pct}%), net margin would be "
            f"{worst_case_net_margin_pct:.1f}% of order value, below min_margin_floor_pct "
            f"({limits.min_margin_floor_pct}%). Lower max_discount_pct or raise gross_margin_pct."
        )

    implied_monthly = limits.daily_budget_inr * 30
    if implied_monthly > limits.campaign_budget_inr * 1.5:
        warnings.append(
            f"daily_budget_inr ({limits.daily_budget_inr}) x 30 = Rs {implied_monthly:,.0f}/month, "
            f"well above campaign_budget_inr (Rs {limits.campaign_budget_inr:,.0f}) — "
            "the daily cap will rarely bind; campaign pacing is doing all the work."
        )

    if limits.cooldown_days_after_offer * limits.max_offers_per_week > 14:
        warnings.append(
            f"cooldown_days_after_offer ({limits.cooldown_days_after_offer}) is long enough that "
            f"max_offers_per_week ({limits.max_offers_per_week}) can never actually be reached."
        )

    if limits.quiet_hours_start_ist == limits.quiet_hours_end_ist:
        warnings.append("quiet_hours_start_ist equals quiet_hours_end_ist — this blocks offers 24 hours a day.")

    catalogue_kinds = {o.kind for o in catalogue.offers}
    for kind in limits.abuse_allowed_offer_kinds:
        if kind not in catalogue_kinds:
            warnings.append(f"abuse.yaml allows offer kind '{kind}', but no catalogue offer has that kind.")

    missing = CORE_OFFER_TYPES - {o.type for o in catalogue.offers}
    if missing:
        warnings.append(f"offer_catalogue.yaml is missing expected core offer type(s): {sorted(missing)}")

    return warnings


def main() -> int:
    catalogue = load_catalogue()
    limits = load_limits()
    warnings = check_conflicts(catalogue, limits)
    if not warnings:
        print("No conflicts found across offer_catalogue.yaml / limits.yaml / fairness.yaml / abuse.yaml.")
        return 0
    print(f"{len(warnings)} conflict(s) found:\n")
    for w in warnings:
        print(f"  - {w}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
