from offerpilot.bot.cards import format_offer_message
from offerpilot.db.models import Customer
from offerpilot.rules.schema import Offer


def _customer(**overrides) -> Customer:
    defaults = dict(name="Test User", city="Ludhiana", city_tier="tier2", language="en")
    defaults.update(overrides)
    return Customer(**defaults)


def test_percent_placeholder_is_substituted_with_the_actual_value():
    offer = Offer(
        type="win_back_discount", kind="percent_off", value=20,
        label_en="{pct}% off your next order", label_hi="x", label_pa="x",
    )
    message = format_offer_message(_customer(), offer)
    assert "20%" in message
    assert "{pct}" not in message


def test_offer_without_placeholder_is_unaffected():
    offer = Offer(
        type="free_shipping", kind="free_shipping", value=0,
        label_en="Free shipping on your next order", label_hi="x", label_pa="x",
    )
    message = format_offer_message(_customer(), offer)
    assert "Free shipping on your next order" in message


def test_no_offer_uses_the_silence_text_not_the_empty_catalogue_label():
    offer = Offer(type="no_offer", kind="none", value=0, label_en="", label_hi="", label_pa="")
    message = format_offer_message(_customer(language="pa"), offer)
    assert "koi nava offer nahi" in message
