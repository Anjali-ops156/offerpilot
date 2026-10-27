import pytest

from offerpilot.bot.i18n import SUPPORTED_LANGUAGES, TRANSLATIONS, t


def test_every_key_has_every_supported_language():
    missing = []
    for key, variants in TRANSLATIONS.items():
        for lang in SUPPORTED_LANGUAGES:
            if lang not in variants or not variants[lang].strip():
                missing.append((key, lang))
    assert missing == []


def test_t_falls_back_to_english_for_unsupported_language():
    assert t("stop_confirm", "fr") == TRANSLATIONS["stop_confirm"]["en"]


def test_t_formats_placeholders():
    result = t("preferences_menu", "en", language="en", frequency=2)
    assert "en" in result and "2" in result


@pytest.mark.parametrize("lang", sorted(SUPPORTED_LANGUAGES))
def test_t_returns_the_right_language(lang):
    assert t("stop_confirm", lang) == TRANSLATIONS["stop_confirm"][lang]
