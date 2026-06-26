"""i18n — minimal internationalization helper for TTMEvolve.

v1.3.0 brings first-class i18n so the LLM prompts, agent messages, and
runtime diagnostics can be served in the user's preferred language.

Design:
- Translation files are JSON, organized by locale under i18n/.
- `t(key, **kwargs)` is the main entry point; missing keys fall back to
  the key string so we never silently swallow a missing translation.
- Locale resolution order: explicit arg > user preference > system > en-US.
- Test-friendly: the helper exposes `set_locale()` and `clear_cache()`.

The module deliberately avoids heavyweight i18n libraries (gettext, i18next)
to keep the embedded runtime small.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional


I18N_VERSION = "i18n.v1"


DEFAULT_LOCALE = "en-US"
SUPPORTED_LOCALES = ("en-US", "zh-CN")
LOCALE_DIR = Path(__file__).resolve().parent.parent / "i18n"


_lock = threading.RLock()
_state: Dict[str, Any] = {
    "locale": DEFAULT_LOCALE,
    "cache": {},  # locale -> {key: translation}
}


def _load_locale_file(locale: str) -> Dict[str, str]:
    """Load a locale's translation JSON, returning {} on missing/corrupt files."""
    path = LOCALE_DIR / f"{locale}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def _resolve_locale(explicit: Optional[str] = None) -> str:
    """Resolve which locale to use, with a deterministic fallback chain."""
    if explicit and explicit in SUPPORTED_LOCALES:
        return explicit
    if explicit:
        # Unknown explicit — try the language part (e.g. "zh-TW" -> "zh-CN").
        prefix = explicit.split("-")[0].lower()
        for supported in SUPPORTED_LOCALES:
            if supported.split("-")[0].lower() == prefix:
                return supported
    preferred = _state.get("locale")
    if preferred in SUPPORTED_LOCALES:
        return preferred
    env_locale = os.environ.get("TTM_LOCALE")
    if env_locale:
        return _resolve_locale(env_locale)
    return DEFAULT_LOCALE


def get_locale() -> str:
    """Return the currently active locale."""
    return _state["locale"]


def set_locale(locale: str) -> None:
    """Switch the active locale (clears the translation cache)."""
    resolved = _resolve_locale(locale)
    with _lock:
        _state["locale"] = resolved
        _state["cache"].pop(resolved, None)


def clear_cache() -> None:
    """Drop the entire translation cache (mostly for tests)."""
    with _lock:
        _state["cache"].clear()


def t(key: str, locale: Optional[str] = None, **kwargs: Any) -> str:
    """Translate `key` to the active (or specified) locale.

    Returns the key itself if no translation is found, so callers can
    always see what they missed. Substitutions use `{name}` placeholders
    and `str.format(**kwargs)`.
    """
    target = _resolve_locale(locale)
    with _lock:
        cache = _state["cache"]
    if target not in cache:
        cache[target] = _load_locale_file(target)

    translated = cache.get(target, {}).get(key)
    if translated is None and target != DEFAULT_LOCALE:
        # Fall back to the default locale so missing keys still produce
        # *some* localized text instead of just the key.
        fallback = cache.get(DEFAULT_LOCALE)
        if fallback is None:
            fallback = _load_locale_file(DEFAULT_LOCALE)
            cache[DEFAULT_LOCALE] = fallback
        translated = fallback.get(key)

    if translated is None:
        return key  # last-resort fallback: the key itself.

    try:
        return translated.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        # Bad placeholder in the translation; return raw text rather than
        # crashing the caller.
        return translated


def available_locales() -> tuple:
    """Return the list of locales we ship with."""
    return tuple(SUPPORTED_LOCALES)


def has_translation(key: str, locale: Optional[str] = None) -> bool:
    """Check whether a translation is available for `key`."""
    target = _resolve_locale(locale)
    with _lock:
        cache = _state["cache"]
    if target not in cache:
        cache[target] = _load_locale_file(target)
    return key in cache.get(target, {})


def pluralize(key_singular: str, key_plural: str, count: int, locale: Optional[str] = None, **kwargs: Any) -> str:
    """Pick singular vs plural translation based on count."""
    template = key_singular if count == 1 else key_plural
    return t(template, locale=locale, count=count, **kwargs)