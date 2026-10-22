from offerpilot.rules.conflict_checker import check_conflicts
from offerpilot.rules.engine import load_catalogue, load_limits
from offerpilot.rules.schema import Offer


def test_current_rules_have_no_conflicts():
    """Regression guard: the shipped rules/*.yaml must always pass clean."""
    assert check_conflicts(load_catalogue(), load_limits()) == []


def test_catches_offer_above_global_discount_cap():
    catalogue = load_catalogue()
    limits = load_limits()
    bad = catalogue.model_copy(deep=True)
    bad.offers.append(Offer(
        type="rogue", kind="percent_off", value=limits.max_discount_pct + 5,
        label_en="x", label_hi="x", label_pa="x",
    ))
    warnings = check_conflicts(bad, limits)
    assert any("rogue" in w and "exceeds max_discount_pct" in w for w in warnings)


def test_catches_tier_fairness_inversion():
    catalogue = load_catalogue()
    limits = load_limits().model_copy(update={
        "win_back_discount_pct_by_tier": {"gold": 10, "silver": 17, "bronze": 15},
    })
    warnings = check_conflicts(catalogue, limits)
    assert any("LOWER than" in w for w in warnings)


def test_catches_unachievable_margin_floor():
    catalogue = load_catalogue()
    limits = load_limits().model_copy(update={"gross_margin_pct": 15, "max_discount_pct": 20, "min_margin_floor_pct": 10})
    warnings = check_conflicts(catalogue, limits)
    assert any("min_margin_floor_pct" in w for w in warnings)


def test_catches_degenerate_quiet_hours():
    catalogue = load_catalogue()
    limits = load_limits().model_copy(update={"quiet_hours_start_ist": 9, "quiet_hours_end_ist": 9})
    warnings = check_conflicts(catalogue, limits)
    assert any("24 hours a day" in w for w in warnings)


def test_catches_duplicate_offer_type():
    catalogue = load_catalogue()
    limits = load_limits()
    bad = catalogue.model_copy(deep=True)
    bad.offers.append(bad.offers[0].model_copy())
    warnings = check_conflicts(bad, limits)
    assert any("Duplicate offer type" in w for w in warnings)
