import pytest

from offerpilot.features.next_best_action import next_best_action_score, offer_cost_inr, rank_offers, simulate_margin
from offerpilot.rules.engine import load_catalogue, load_limits


@pytest.fixture(scope="module")
def catalogue():
    return load_catalogue()


@pytest.fixture(scope="module")
def limits():
    return load_limits()


def test_offer_cost_percent_off_scales_with_order_value(limits):
    offer = next(o for o in load_catalogue().offers if o.kind == "percent_off")
    assert offer_cost_inr(1000, offer, limits) == 1000 * offer.value / 100


def test_offer_cost_free_shipping_is_fixed(catalogue, limits):
    offer = catalogue.get("free_shipping")
    assert offer_cost_inr(5000, offer, limits) == limits.shipping_cost_inr


def test_offer_cost_no_offer_is_zero(catalogue, limits):
    offer = catalogue.get("no_offer")
    assert offer_cost_inr(5000, offer, limits) == 0.0


def test_bigger_discount_lowers_net_margin_pct(catalogue, limits):
    offer = catalogue.get("win_back_discount")
    sim = simulate_margin(1000, offer, limits)
    assert sim.net_margin_pct < limits.gross_margin_pct  # discount eats into gross margin


def test_rank_offers_prefers_higher_score(catalogue, limits):
    # High enough uplift that win_back_discount's margin gain clears its own cost.
    uplift_by_offer = {"win_back_discount": 0.6, "free_shipping": 0.1, "no_offer": 0.0}
    ranked = rank_offers(uplift_by_offer, 1000, catalogue.offers, limits)
    assert ranked[0].offer_type == "win_back_discount"
    assert ranked[0].score > 0
    assert ranked[0].score >= ranked[-1].score


def test_zero_uplift_means_no_offer_beats_every_costed_offer(catalogue, limits):
    # Zero uplift -> any offer with a real cost (percent_off/flat/points/bogo/
    # shipping) scores negative; no_offer (free, zero-effect) scores exactly
    # 0 and must beat all of them. Zero-cost nudge/early-access kinds also
    # score 0 and are excluded here deliberately — this test is about costed
    # offers specifically.
    costed = {o.type for o in catalogue.offers if o.kind not in ("nudge", "early_access", "none")}
    uplift_by_offer = {t: 0.0 for t in costed}
    ranked = rank_offers(uplift_by_offer, 1000, catalogue.offers, limits)
    no_offer_score = next(r for r in ranked if r.offer_type == "no_offer").score
    for r in ranked:
        if r.offer_type in costed:
            assert no_offer_score >= r.score
