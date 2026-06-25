"""Tests for the auto-update client."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core import updater_client
from core.updater_client import (
    UPDATER_CLIENT_VERSION,
    DEFAULT_CURRENT_VERSION,
    check_for_update,
    is_newer_version,
    latest_release,
    percent_complete,
    release_card,
    summarize_release,
)


# ---------- version comparison ----------


def test_is_newer_version_major_bump():
    assert is_newer_version("2.0.0", "1.99.99") is True
    assert is_newer_version("1.99.99", "2.0.0") is False


def test_is_newer_version_minor_bump():
    assert is_newer_version("1.1.0", "1.0.99") is True
    assert is_newer_version("1.0.99", "1.1.0") is False


def test_is_newer_version_patch_bump():
    assert is_newer_version("1.0.1", "1.0.0") is True
    assert is_newer_version("1.0.0", "1.0.1") is False


def test_is_newer_version_equal_returns_false():
    assert is_newer_version("1.0.0", "1.0.0") is False


def test_is_newer_version_pre_release_lower_than_release():
    """A release is newer than a prerelease of the same base; a prerelease
    of the same base as the current release is older (i.e. not newer)."""
    # rc is older than release → not newer
    assert is_newer_version("1.0.0-rc.1", "1.0.0") is False
    # release is newer than rc → newer
    assert is_newer_version("1.0.0", "1.0.0-rc.1") is True


def test_is_newer_version_handles_malformed_components():
    assert is_newer_version("1.0.x", "1.0.0") is False
    assert is_newer_version("1.0.0", "1.0.x") is False


def test_is_newer_version_handles_different_lengths():
    assert is_newer_version("1.0.0.1", "1.0.0") is True
    assert is_newer_version("1.0.0", "1.0.0.1") is False


# ---------- summarize_release ----------


def test_summarize_release_with_notes():
    notes = "Line 1\nLine 2\nLine 3\nLine 4"
    summary = summarize_release(notes, max_lines=2)
    assert summary == "Line 1\nLine 2"


def test_summarize_release_none():
    assert summarize_release(None, 3) == "(no release notes provided)"


def test_summarize_release_empty_string():
    assert summarize_release("", 3) == "(empty release notes)"


# ---------- percent_complete ----------


def test_percent_complete_zero_total():
    assert percent_complete(50, 0) == 0.0


def test_percent_complete_half():
    assert percent_complete(50, 100) == 50.0


def test_percent_complete_full():
    assert percent_complete(100, 100) == 100.0


def test_percent_complete_clamps_overflow():
    assert percent_complete(200, 100) == 100.0


# ---------- release_card ----------


def test_release_card_includes_required_fields():
    info = updater_client.UpdateInfo(
        current_version="1.0.0",
        latest_version="1.0.0",
        available=False,
        release_notes=None,
        pub_date=None,
        source="fallback",
    )
    card = release_card(info)
    assert "Current: 1.0.0" in card
    assert "Available: no" in card
    assert "Source: fallback" in card


def test_release_card_includes_release_notes_when_present():
    info = updater_client.UpdateInfo(
        current_version="1.0.0",
        latest_version="1.1.0",
        available=True,
        release_notes="## What's new\n- Better settings\n- Faster startup",
        pub_date="2026-06-26",
        source="github",
    )
    card = release_card(info)
    assert "Better settings" in card
    assert "2026-06-26" in card


# ---------- latest_release (offline fallback) ----------


def test_latest_release_falls_back_when_offline(monkeypatch):
    """Without network, latest_release returns a fallback UpdateInfo."""
    from core import updater_client as uc

    monkeypatch.setattr(uc, "_fetch_github_release", lambda: None)
    info = latest_release(current_version="0.9.0")
    assert info.available is False
    assert info.source == "fallback"
    assert info.current_version == "0.9.0"


def test_latest_release_detects_update_when_newer(monkeypatch):
    from core import updater_client as uc

    monkeypatch.setattr(
        uc,
        "_fetch_github_release",
        lambda: {
            "tag_name": "v1.5.0",
            "body": "big release",
            "published_at": "2026-07-01",
        },
    )
    info = latest_release(current_version="1.0.0")
    assert info.available is True
    assert info.latest_version == "1.5.0"
    assert info.source == "github"


def test_latest_release_no_update_when_equal(monkeypatch):
    from core import updater_client as uc

    monkeypatch.setattr(
        uc,
        "_fetch_github_release",
        lambda: {"tag_name": "v1.0.0", "body": None, "published_at": None},
    )
    info = latest_release(current_version="1.0.0")
    assert info.available is False


def test_check_for_update_delegates_to_latest_release(monkeypatch):
    from core import updater_client as uc

    monkeypatch.setattr(
        uc,
        "latest_release",
        lambda current_version="1.0.0": uc.UpdateInfo(
            current_version=current_version,
            latest_version="2.0.0",
            available=True,
            release_notes="v2",
            pub_date="2026-07-15",
            source="github",
        ),
    )
    info = check_for_update()
    assert info.latest_version == "2.0.0"
    assert info.available is True


# ---------- module constants ----------


def test_module_version_constant():
    assert updater_client.UPDATER_CLIENT_VERSION == "updater-client.v1"


def test_default_current_version_is_v090():
    assert DEFAULT_CURRENT_VERSION == "0.9.0"


# ---------- dataclass ----------


def test_update_info_to_dict_round_trip():
    info = updater_client.UpdateInfo(
        current_version="1.0.0",
        latest_version="2.0.0",
        available=True,
        release_notes="notes",
        pub_date="2026-07-01",
        source="github",
    )
    d = info.to_dict()
    assert d["current_version"] == "1.0.0"
    assert d["latest_version"] == "2.0.0"
    assert d["available"] is True
    assert d["source"] == "github"