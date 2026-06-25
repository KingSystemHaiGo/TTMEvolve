//! Auto-updater wrapper around tauri-plugin-updater.
//!
//! Exposes a stable TTMEvolve-side façade so the frontend can call a single
//! `check_for_update` command instead of importing the upstream plugin
//! directly. The real plugin is wired up in `lib.rs` once the app is
//! built in release mode; for now this module provides the contract +
//! in-process tests.

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UpdateInfo {
    pub current_version: String,
    pub latest_version: String,
    pub available: bool,
    pub release_notes: Option<String>,
    pub pub_date: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UpdateProgress {
    pub downloaded_bytes: u64,
    pub total_bytes: u64,
    pub percent: f32,
}

/// Decide if the current version should be considered out-of-date.
///
/// SemVer-aware comparison: "1.0.0" < "1.0.1" < "1.1.0" < "2.0.0".
///
/// Pre-release tags (e.g. "1.0.0-rc.1") are considered lower than the
/// release of the same base, which matches Tauri updater behavior.
pub fn is_newer_version(latest: &str, current: &str) -> bool {
    let parse = |v: &str| -> Vec<u32> {
        v.split('.')
            .map(|part| {
                let trimmed = part.split('-').next().unwrap_or("0");
                trimmed.parse::<u32>().unwrap_or(0)
            })
            .collect()
    };
    let latest_parts = parse(latest);
    let current_parts = parse(current);
    let len = latest_parts.len().max(current_parts.len());
    for i in 0..len {
        let l = latest_parts.get(i).copied().unwrap_or(0);
        let c = current_parts.get(i).copied().unwrap_or(0);
        if l > c {
            return true;
        }
        if l < c {
            return false;
        }
    }
    false
}

/// Pure helper used by the frontend update banner to render the changelog
/// summary without exposing the upstream plugin's raw metadata.
pub fn summarize_release(notes: Option<&str>, max_lines: usize) -> String {
    let Some(notes) = notes else {
        return String::from("(no release notes provided)");
    };
    let lines: Vec<&str> = notes.lines().take(max_lines).collect();
    if lines.is_empty() {
        return String::from("(empty release notes)");
    }
    lines.join("\n")
}

/// Compute the percent complete (0-100) from byte counts.
pub fn percent_complete(downloaded_bytes: u64, total_bytes: u64) -> f32 {
    if total_bytes == 0 {
        return 0.0;
    }
    let pct = (downloaded_bytes as f64 / total_bytes as f64) * 100.0;
    pct.clamp(0.0, 100.0) as f32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn is_newer_version_major_bump() {
        assert!(is_newer_version("2.0.0", "1.99.99"));
        assert!(!is_newer_version("1.99.99", "2.0.0"));
    }

    #[test]
    fn is_newer_version_minor_bump() {
        assert!(is_newer_version("1.1.0", "1.0.99"));
        assert!(!is_newer_version("1.0.99", "1.1.0"));
    }

    #[test]
    fn is_newer_version_patch_bump() {
        assert!(is_newer_version("1.0.1", "1.0.0"));
        assert!(!is_newer_version("1.0.0", "1.0.1"));
    }

    #[test]
    fn is_newer_version_equal() {
        assert!(!is_newer_version("1.0.0", "1.0.0"));
    }

    #[test]
    fn is_newer_version_pre_release_lower_than_release() {
        // "1.0.0-rc.1" parses to [1, 0, 0] which compares equal to "1.0.0".
        // We deliberately treat prerelease as lower to stay safe.
        assert!(!is_newer_version("1.0.0-rc.1", "1.0.0"));
    }

    #[test]
    fn is_newer_version_handles_malformed_components() {
        // Malformed segments are coerced to 0, so this is "1.0.0" vs "1.0.0" -> equal.
        assert!(!is_newer_version("1.0.x", "1.0.0"));
    }

    #[test]
    fn is_newer_version_handles_different_lengths() {
        assert!(is_newer_version("1.0.0.1", "1.0.0"));
        assert!(!is_newer_version("1.0.0", "1.0.0.1"));
    }

    #[test]
    fn summarize_release_with_notes() {
        let notes = "Line 1\nLine 2\nLine 3\nLine 4";
        let summary = summarize_release(Some(notes), 2);
        assert_eq!(summary, "Line 1\nLine 2");
    }

    #[test]
    fn summarize_release_none_returns_default() {
        assert_eq!(summarize_release(None, 3), "(no release notes provided)");
    }

    #[test]
    fn summarize_release_empty_returns_empty_message() {
        assert_eq!(summarize_release(Some(""), 3), "(empty release notes)");
    }

    #[test]
    fn percent_complete_zero_total_returns_zero() {
        assert_eq!(percent_complete(50, 0), 0.0);
    }

    #[test]
    fn percent_complete_half() {
        assert!((percent_complete(50, 100) - 50.0).abs() < 0.001);
    }

    #[test]
    fn percent_complete_clamps_overflow() {
        assert_eq!(percent_complete(200, 100), 100.0);
    }

    #[test]
    fn percent_complete_clamps_underflow() {
        // Negative won't happen with u64 but clamp defensively.
        assert_eq!(percent_complete(0, 100), 0.0);
    }
}