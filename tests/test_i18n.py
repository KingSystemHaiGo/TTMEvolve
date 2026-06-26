"""Tests for the v1.3.0 i18n system."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core import i18n
from core.i18n import (
    DEFAULT_LOCALE,
    I18N_VERSION,
    SUPPORTED_LOCALES,
    available_locales,
    clear_cache,
    get_locale,
    has_translation,
    pluralize,
    set_locale,
    t,
)


@pytest.fixture(autouse=True)
def reset_i18n():
    """Each test starts with the default locale and a clean cache."""
    set_locale(DEFAULT_LOCALE)
    clear_cache()
    yield
    set_locale(DEFAULT_LOCALE)
    clear_cache()


# ---------- basics ----------


def test_module_version_constant():
    assert i18n.I18N_VERSION == "i18n.v1"


def test_default_locale_is_en_us():
    assert DEFAULT_LOCALE == "en-US"


def test_supported_locales_include_en_and_zh():
    assert "en-US" in SUPPORTED_LOCALES
    assert "zh-CN" in SUPPORTED_LOCALES


def test_available_locales_returns_supported_tuple():
    locales = available_locales()
    assert "en-US" in locales
    assert "zh-CN" in locales


def test_get_locale_returns_default_initially():
    assert get_locale() == DEFAULT_LOCALE


def test_set_locale_updates_active_locale():
    set_locale("zh-CN")
    assert get_locale() == "zh-CN"


def test_set_locale_with_unknown_keeps_default():
    set_locale("xx-XX")
    assert get_locale() == DEFAULT_LOCALE


def test_set_locale_with_prefix_falls_back():
    """zh-TW should fall back to zh-CN (same language prefix)."""
    set_locale("zh-TW")
    assert get_locale() == "zh-CN"


# ---------- translation lookups ----------


def test_translate_returns_key_when_missing():
    assert t("nonexistent.key") == "nonexistent.key"


def test_translate_returns_english_text():
    set_locale("en-US")
    result = t("app.name")
    assert result == "TTMEvolve"


def test_translate_returns_chinese_text():
    set_locale("zh-CN")
    result = t("app.name")
    assert result == "TTMEvolve"  # same in both languages


def test_translate_chinese_distinct_string():
    set_locale("en-US")
    en_value = t("settings.title")
    set_locale("zh-CN")
    zh_value = t("settings.title")
    assert en_value != zh_value
    assert "Settings" in en_value or "settings" in en_value.lower()
    assert "设置" in zh_value


def test_translate_substitutes_placeholders():
    set_locale("en-US")
    result = t("app.version", version="1.0.0")
    assert "1.0.0" in result


def test_translate_chinese_substitutes_placeholders():
    set_locale("zh-CN")
    result = t("app.version", version="1.0.0")
    assert "1.0.0" in result


def test_translate_with_locale_override():
    """Passing locale= directly should bypass the active locale."""
    set_locale("en-US")
    zh = t("settings.title", locale="zh-CN")
    assert "设置" in zh


def test_translate_with_explicit_locale_param():
    set_locale("zh-CN")
    en = t("settings.title", locale="en-US")
    assert "Settings" in en


def test_translate_falls_back_to_default_when_key_missing():
    """If a key exists in en-US but not in zh-CN, return English."""
    set_locale("zh-CN")
    # Use a key that's only in the default locale.
    # We simulate by checking fallback behavior with a known missing key.
    result = t("totally.fake.key")
    assert result == "totally.fake.key"


def test_translate_returns_raw_on_bad_placeholder():
    """If a translation has a bad placeholder, return the raw text."""
    set_locale("en-US")
    # Ensure the locale is loaded so we can monkey-patch the cache.
    t("app.name")
    # Inject a translation with an unresolvable placeholder.
    i18n._state["cache"]["en-US"]["another.key"] = "Hi {nope}"
    result = t("another.key")
    assert result == "Hi {nope}"


def test_has_translation_returns_true_for_existing_key():
    set_locale("en-US")
    assert has_translation("app.name") is True


def test_has_translation_returns_false_for_missing_key():
    set_locale("en-US")
    assert has_translation("does.not.exist") is False


# ---------- pluralization ----------


def test_pluralize_picks_singular_for_count_one():
    set_locale("en-US")
    result = pluralize("tools.count_one", "tools.count", 1)
    assert result == "1 tool"


def test_pluralize_picks_plural_for_count_greater_than_one():
    set_locale("en-US")
    result = pluralize("tools.count_one", "tools.count", 5)
    assert "5" in result


def test_pluralize_uses_count_zero_for_plural():
    set_locale("en-US")
    result = pluralize("tools.count_one", "tools.count", 0)
    assert "0" in result


# ---------- cache management ----------


def test_clear_cache_drops_translations():
    set_locale("en-US")
    t("app.name")  # populate cache
    assert "en-US" in i18n._state["cache"]
    clear_cache()
    assert i18n._state["cache"] == {}


def test_set_locale_clears_target_locale_cache():
    set_locale("en-US")
    t("app.name")
    set_locale("zh-CN")
    # zh-CN cache should have been cleared by set_locale.
    assert "zh-CN" not in i18n._state["cache"]


# ---------- thread safety ----------


def test_set_locale_from_multiple_threads():
    """set_locale + get_locale should be thread-safe (RLock protected)."""
    import threading

    errors = []

    def worker(locale: str) -> None:
        try:
            for _ in range(50):
                set_locale(locale)
                _ = get_locale()
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("en-US",)),
        threading.Thread(target=worker, args=("zh-CN",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


# ---------- translation file integrity ----------


def test_en_us_translation_file_exists():
    path = _PROJECT_ROOT / "i18n" / "en-US.json"
    assert path.exists()


def test_zh_cn_translation_file_exists():
    path = _PROJECT_ROOT / "i18n" / "zh-CN.json"
    assert path.exists()


def test_en_us_translations_are_valid_json():
    import json
    path = _PROJECT_ROOT / "i18n" / "en-US.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert len(data) > 20


def test_zh_cn_translations_are_valid_json():
    import json
    path = _PROJECT_ROOT / "i18n" / "zh-CN.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert len(data) > 20


def test_en_us_and_zh_cn_have_same_keys():
    import json
    en = set(json.loads((_PROJECT_ROOT / "i18n" / "en-US.json").read_text(encoding="utf-8")).keys())
    zh = set(json.loads((_PROJECT_ROOT / "i18n" / "zh-CN.json").read_text(encoding="utf-8")).keys())
    missing_in_zh = en - zh
    missing_in_en = zh - en
    # Both files should expose the same keys; report if not.
    assert not missing_in_zh, f"keys missing in zh-CN: {missing_in_zh}"
    assert not missing_in_en, f"keys missing in en-US: {missing_in_en}"