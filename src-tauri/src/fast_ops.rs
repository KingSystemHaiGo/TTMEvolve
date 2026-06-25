//! Fast operations — Rust-side replacements for Python hot paths.
//!
//! Replaces Python implementations for:
//!   * port probing (used by server_manager + maker_setup + runtime diagnostic)
//!   * log tailing (used by desktop / maker / browser log viewers)
//!   * file size / directory listing (used by portable diagnostics + IDE)
//!
//! These run inside the Tauri process so they don't incur Python startup,
//! interpreter overhead, or any GIL contention. When the Python backend needs
//! them, it calls through the tauri command layer (see commands::mod.rs).

use std::fs;
use std::io::{Read, Seek, SeekFrom};
use std::net::{TcpListener, TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::{Deserialize, Serialize};

/// How many bytes to read at most when tailing a log file.
const DEFAULT_TAIL_BYTES: u64 = 256 * 1024;

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct PortProbeResult {
    pub host: String,
    pub port: u16,
    pub available: bool,
    pub latency_ms: Option<f64>,
}

/// Probe a single TCP port and report whether it accepts a connection.
pub fn probe_port(host: &str, port: u16, timeout_ms: u64) -> PortProbeResult {
    let addr = match (host, port).to_socket_addrs() {
        Ok(mut addrs) => match addrs.next() {
            Some(a) => a,
            None => {
                return PortProbeResult {
                    host: host.to_string(),
                    port,
                    available: false,
                    latency_ms: None,
                };
            }
        },
        Err(_) => {
            return PortProbeResult {
                host: host.to_string(),
                port,
                available: false,
                latency_ms: None,
            };
        }
    };
    let started = std::time::Instant::now();
    let conn = TcpStream::connect_timeout(&addr, Duration::from_millis(timeout_ms));
    let latency = started.elapsed().as_secs_f64() * 1000.0;
    match conn {
        Ok(stream) => {
            drop(stream);
            PortProbeResult {
                host: host.to_string(),
                port,
                available: true,
                latency_ms: Some(latency),
            }
        }
        Err(_) => PortProbeResult {
            host: host.to_string(),
            port,
            available: false,
            latency_ms: Some(latency),
        },
    }
}

/// Find the first available TCP port in `[start, start+limit]` (inclusive).
pub fn find_available_port(host: &str, start: u16, limit: u16, timeout_ms: u64) -> Option<u16> {
    for offset in 0..=limit {
        let port = start.saturating_add(offset);
        if probe_port(host, port, timeout_ms).available {
            return Some(port);
        }
    }
    None
}

/// Quick port_available helper (mirrors server_manager::port_available).
pub fn port_available(host: &str, port: u16) -> bool {
    TcpListener::bind((host, port)).is_ok()
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct LogTail {
    pub path: String,
    pub total_bytes: u64,
    pub tail_bytes: u64,
    pub lines: Vec<String>,
    pub truncated: bool,
}

/// Read the last `max_bytes` of a log file and split into lines.
pub fn tail_log(path: &Path, max_bytes: u64) -> std::io::Result<LogTail> {
    let metadata = fs::metadata(path)?;
    let total_bytes = metadata.len();
    let read_bytes = max_bytes.min(total_bytes);
    let mut file = fs::File::open(path)?;
    if total_bytes > read_bytes {
        file.seek(SeekFrom::End(-(read_bytes as i64)))?;
    }
    let mut buffer = Vec::with_capacity(read_bytes as usize);
    file.take(read_bytes).read_to_end(&mut buffer)?;
    let text = String::from_utf8_lossy(&buffer);
    let lines: Vec<String> = text.lines().map(|s| s.to_string()).collect();
    Ok(LogTail {
        path: path.to_string_lossy().into_owned(),
        total_bytes,
        tail_bytes: read_bytes,
        truncated: total_bytes > read_bytes,
        lines,
    })
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct DirSizeResult {
    pub path: String,
    pub file_count: usize,
    pub total_bytes: u64,
}

/// Recursively compute directory size without following symlinks.
pub fn dir_size(path: &Path) -> std::io::Result<DirSizeResult> {
    let mut total_bytes: u64 = 0;
    let mut file_count: usize = 0;
    let mut stack = vec![path.to_path_buf()];
    while let Some(current) = stack.pop() {
        let entries = match fs::read_dir(&current) {
            Ok(entries) => entries,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let entry_path = entry.path();
            let file_type = match entry.file_type() {
                Ok(ft) => ft,
                Err(_) => continue,
            };
            if file_type.is_file() {
                file_count += 1;
                if let Ok(meta) = entry.metadata() {
                    total_bytes += meta.len();
                }
            } else if file_type.is_dir() {
                stack.push(entry_path);
            }
        }
    }
    Ok(DirSizeResult {
        path: path.to_string_lossy().into_owned(),
        file_count,
        total_bytes,
    })
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct FileEntry {
    pub name: String,
    pub path: String,
    pub is_dir: bool,
    pub size_bytes: u64,
}

/// List a directory (non-recursive) — replaces Python's os.listdir.
pub fn list_dir(path: &Path) -> std::io::Result<Vec<FileEntry>> {
    let mut entries = Vec::new();
    for entry in fs::read_dir(path)?.flatten() {
        let file_type = entry.file_type().ok();
        let is_dir = file_type.map(|ft| ft.is_dir()).unwrap_or(false);
        let size_bytes = entry.metadata().map(|m| m.len()).unwrap_or(0);
        entries.push(FileEntry {
            name: entry.file_name().to_string_lossy().into_owned(),
            path: entry.path().to_string_lossy().into_owned(),
            is_dir,
            size_bytes,
        });
    }
    Ok(entries)
}

/// Format a byte count using IEC binary units (KiB / MiB / GiB).
pub fn format_bytes(bytes: u64) -> String {
    const UNITS: &[&str] = &["B", "KiB", "MiB", "GiB", "TiB"];
    if bytes < 1024 {
        return format!("{}B", bytes);
    }
    let mut value = bytes as f64;
    let mut unit_index = 0;
    while value >= 1024.0 && unit_index < UNITS.len() - 1 {
        value /= 1024.0;
        unit_index += 1;
    }
    format!("{:.2}{}", value, UNITS[unit_index])
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn format_bytes_handles_zero() {
        assert_eq!(format_bytes(0), "0B");
    }

    #[test]
    fn format_bytes_kib() {
        assert_eq!(format_bytes(1024), "1.00KiB");
    }

    #[test]
    fn format_bytes_mib() {
        assert_eq!(format_bytes(1024 * 1024), "1.00MiB");
    }

    #[test]
    fn format_bytes_gib() {
        assert_eq!(format_bytes(2 * 1024 * 1024 * 1024), "2.00GiB");
    }

    #[test]
    fn probe_port_returns_unavailable_for_high_port() {
        // Pick a port very unlikely to be open on test hosts.
        let result = probe_port("127.0.0.1", 1, 50);
        assert!(!result.available);
    }

    #[test]
    fn port_available_matches_listener_bind() {
        // Bind a listener to claim a port.
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("addr").port();
        assert!(!port_available("127.0.0.1", port));
        drop(listener);
    }

    #[test]
    fn tail_log_returns_recent_lines() {
        let dir = std::env::temp_dir();
        let path = dir.join("ttmevolve_test_tail.log");
        let mut file = fs::File::create(&path).expect("create");
        for i in 0..100 {
            writeln!(file, "line {}", i).expect("write");
        }
        drop(file);
        let tail = tail_log(&path, 1024).expect("tail");
        assert!(tail.lines.len() > 0);
        assert!(tail.lines.last().unwrap().contains("line"));
        let _ = fs::remove_file(&path);
    }

    #[test]
    fn dir_size_returns_zero_for_empty_dir() {
        let dir = std::env::temp_dir().join("ttmevolve_test_empty_dir");
        let _ = fs::create_dir_all(&dir);
        let result = dir_size(&dir).expect("dir_size");
        assert_eq!(result.total_bytes, 0);
        assert_eq!(result.file_count, 0);
        let _ = fs::remove_dir(&dir);
    }

    #[test]
    fn list_dir_returns_files() {
        let dir = std::env::temp_dir().join("ttmevolve_test_list_dir");
        let _ = fs::create_dir_all(&dir);
        fs::write(dir.join("a.txt"), "hello").expect("write");
        let entries = list_dir(&dir).expect("list_dir");
        assert!(entries.iter().any(|e| e.name == "a.txt"));
        let _ = fs::remove_dir_all(&dir);
    }
}