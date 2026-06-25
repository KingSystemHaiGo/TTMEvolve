//! HTTP bridge server — exposes fast_ops commands over HTTP so the Python
//! backend can call into Rust without going through tauri.invoke.
//!
//! Architecture:
//!   Python backend (port 8765)
//!        ↓ HTTP POST /fast_ops/{command}
//!   This bridge server (port 8766, bound to 127.0.0.1)
//!        ↓ calls into fast_ops::* (sync, fast, no GIL)
//!
//! The bridge uses Rust's `std::net::TcpListener` + per-connection thread to
//! avoid pulling in a heavyweight HTTP framework. The request format is:
//!
//!   POST /fast_ops/fast_probe_port HTTP/1.1
//!   Content-Type: application/json
//!   {"host": "127.0.0.1", "port": 8765, "timeout_ms": 200}
//!
//! Response:
//!   HTTP/1.1 200 OK
//!   Content-Type: application/json
//!   {"host": "127.0.0.1", "port": 8765, "available": true, "latency_ms": 0.5}

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

use crate::fast_ops;

const BRIDGE_VERSION: &str = "fast-ops-http-bridge.v1";
const DEFAULT_PORT: u16 = 8766;
const READ_TIMEOUT: Duration = Duration::from_secs(5);
const MAX_REQUEST_BYTES: usize = 64 * 1024;

#[derive(Clone, Debug)]
pub struct BridgeConfig {
    pub host: String,
    pub port: u16,
}

impl Default for BridgeConfig {
    fn default() -> Self {
        Self {
            host: "127.0.0.1".to_string(),
            port: DEFAULT_PORT,
        }
    }
}

pub struct BridgeHandle {
    pub addr: std::net::SocketAddr,
    stop: Arc<std::sync::atomic::AtomicBool>,
}

impl BridgeHandle {
    pub fn stop(&self) {
        self.stop.store(true, std::sync::atomic::Ordering::SeqCst);
    }
}

pub fn start_blocking(config: BridgeConfig) -> Result<BridgeHandle, String> {
    let listener = TcpListener::bind((config.host.as_str(), config.port))
        .map_err(|err| format!("bind {}:{}: {}", config.host, config.port, err))?;
    let addr = listener.local_addr().map_err(|err| err.to_string())?;
    let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let stop_clone = stop.clone();
    thread::spawn(move || {
        while !stop_clone.load(std::sync::atomic::Ordering::SeqCst) {
            match listener.accept() {
                Ok((stream, _)) => {
                    thread::spawn(move || {
                        handle_client(stream);
                    });
                }
                Err(_) => {
                    // Listener probably closed; loop ends.
                    break;
                }
            }
        }
    });
    Ok(BridgeHandle { addr, stop })
}

pub fn start_background(config: BridgeConfig) -> Result<BridgeHandle, String> {
    // Same as start_blocking but returns immediately; the server runs in its
    // own thread until BridgeHandle::stop() is called.
    start_blocking(config)
}

fn handle_client(stream: TcpStream) {
    let _ = stream.set_read_timeout(Some(READ_TIMEOUT));
    let _ = stream.set_write_timeout(Some(READ_TIMEOUT));
    let mut reader = BufReader::new(stream.try_clone().ok());
    let request_line = match reader.by_ref().lines().next() {
        Some(Ok(line)) => line,
        _ => return,
    };
    // Parse request line: METHOD PATH HTTP/1.1
    let mut parts = request_line.split_whitespace();
    let method = parts.next().unwrap_or("");
    let path = parts.next().unwrap_or("");
    if method != "POST" {
        send_response(&stream, 405, r#"{"error":"method not allowed"}"#);
        return;
    }

    // Read headers until blank line.
    let mut content_length: usize = 0;
    loop {
        let line = match reader.by_ref().lines().next() {
            Some(Ok(line)) => line,
            _ => break,
        };
        if line.is_empty() {
            break;
        }
        if let Some(rest) = line.strip_prefix("Content-Length:") {
            content_length = rest.trim().parse().unwrap_or(0);
        } else if let Some(rest) = line.strip_prefix("content-length:") {
            content_length = rest.trim().parse().unwrap_or(0);
        }
    }

    // Read body (limited to MAX_REQUEST_BYTES).
    let body_len = content_length.min(MAX_REQUEST_BYTES);
    let mut body = vec![0u8; body_len];
    if body_len > 0 {
        if reader.read_exact(&mut body).is_err() {
            send_response(&stream, 400, r#"{"error":"failed to read body"}"#);
            return;
        }
    }

    let response_body = handle_request(path, &body);
    let status = if response_body.starts_with(r#"{"error":"#) {
        400
    } else {
        200
    };
    send_response(&stream, status, &response_body);
}

fn send_response(stream: &TcpStream, status: u16, body: &str) {
    let reason = match status {
        200 => "OK",
        400 => "Bad Request",
        404 => "Not Found",
        405 => "Method Not Allowed",
        500 => "Internal Server Error",
        _ => "OK",
    };
    let body_bytes = body.as_bytes();
    let response = format!(
        "HTTP/1.1 {} {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        status,
        reason,
        body_bytes.len()
    );
    let mut stream = stream;
    let _ = stream.write_all(response.as_bytes());
    let _ = stream.write_all(body_bytes);
    let _ = stream.flush();
}

fn handle_request(path: &str, body: &[u8]) -> String {
    // Path: /fast_ops/{command} or /health
    if path == "/health" {
        return json_response(&serde_json::json!({
            "status": "ok",
            "version": BRIDGE_VERSION,
        }));
    }
    let command = match path.strip_prefix("/fast_ops/") {
        Some(name) => name,
        None => {
            return json_error(404, "not_found");
        }
    };
    let payload: serde_json::Value = if body.is_empty() {
        serde_json::json!({})
    } else {
        match serde_json::from_slice(body) {
            Ok(v) => v,
            Err(err) => {
                return json_error(400, &format!("invalid json: {err}"));
            }
        }
    };
    dispatch(command, &payload)
}

fn dispatch(command: &str, payload: &serde_json::Value) -> String {
    match command {
        "fast_probe_port" => {
            let host = payload.get("host").and_then(|v| v.as_str()).unwrap_or("127.0.0.1").to_string();
            let port = payload.get("port").and_then(|v| v.as_u64()).unwrap_or(0) as u16;
            let timeout_ms = payload.get("timeout_ms").and_then(|v| v.as_u64()).unwrap_or(200);
            let result = fast_ops::probe_port(&host, port, timeout_ms);
            json_response(&serde_json::to_value(&result).unwrap_or_default())
        }
        "fast_find_available_port" => {
            let host = payload.get("host").and_then(|v| v.as_str()).unwrap_or("127.0.0.1").to_string();
            let start = payload.get("start").and_then(|v| v.as_u64()).unwrap_or(0) as u16;
            let limit = payload.get("limit").and_then(|v| v.as_u64()).unwrap_or(40) as u16;
            let timeout_ms = payload.get("timeout_ms").and_then(|v| v.as_u64()).unwrap_or(200);
            let result = fast_ops::find_available_port(&host, start, limit, timeout_ms);
            json_response(&serde_json::json!(result))
        }
        "fast_tail_log" => {
            let path = payload.get("path").and_then(|v| v.as_str()).unwrap_or("");
            let max_bytes = payload.get("max_bytes").and_then(|v| v.as_u64()).unwrap_or(262144);
            if path.is_empty() {
                return json_error(400, "missing path");
            }
            match fast_ops::tail_log(std::path::Path::new(path), max_bytes) {
                Ok(tail) => json_response(&serde_json::to_value(&tail).unwrap_or_default()),
                Err(err) => json_error(500, &format!("tail_log: {err}")),
            }
        }
        "fast_dir_size" => {
            let path = payload.get("path").and_then(|v| v.as_str()).unwrap_or("");
            if path.is_empty() {
                return json_error(400, "missing path");
            }
            match fast_ops::dir_size(std::path::Path::new(path)) {
                Ok(size) => json_response(&serde_json::to_value(&size).unwrap_or_default()),
                Err(err) => json_error(500, &format!("dir_size: {err}")),
            }
        }
        "fast_list_dir" => {
            let path = payload.get("path").and_then(|v| v.as_str()).unwrap_or("");
            if path.is_empty() {
                return json_error(400, "missing path");
            }
            match fast_ops::list_dir(std::path::Path::new(path)) {
                Ok(entries) => json_response(&serde_json::to_value(&entries).unwrap_or_default()),
                Err(err) => json_error(500, &format!("list_dir: {err}")),
            }
        }
        "fast_format_bytes" => {
            let bytes = payload.get("bytes").and_then(|v| v.as_u64()).unwrap_or(0);
            let formatted = fast_ops::format_bytes(bytes);
            json_response(&serde_json::json!({ "formatted": formatted }))
        }
        _ => json_error(404, &format!("unknown command: {command}")),
    }
}

fn json_response(value: &serde_json::Value) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "{}".to_string())
}

fn json_error(code: u16, message: &str) -> String {
    format!(r#"{{"error":"{}","code":{}}}"#, message.replace('"', "'"), code)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bridge_config_default() {
        let config = BridgeConfig::default();
        assert_eq!(config.host, "127.0.0.1");
        assert_eq!(config.port, 8766);
    }

    #[test]
    fn json_error_includes_code_and_message() {
        let body = json_error(404, "not_found");
        assert!(body.contains("not_found"));
        assert!(body.contains("404"));
    }

    #[test]
    fn json_response_serializes_value() {
        let v = serde_json::json!({"k": 1});
        let s = json_response(&v);
        assert_eq!(s, r#"{"k":1}"#);
    }

    #[test]
    fn dispatch_unknown_command_returns_error() {
        let payload = serde_json::json!({});
        let response = dispatch("nonexistent", &payload);
        assert!(response.contains("unknown command"));
    }

    #[test]
    fn dispatch_fast_format_bytes() {
        let payload = serde_json::json!({"bytes": 1048576});
        let response = dispatch("fast_format_bytes", &payload);
        assert!(response.contains("1.00MiB"));
    }

    #[test]
    fn dispatch_fast_format_bytes_zero() {
        let payload = serde_json::json!({"bytes": 0});
        let response = dispatch("fast_format_bytes", &payload);
        assert!(response.contains("0B"));
    }

    #[test]
    fn dispatch_fast_probe_port_with_missing_host_uses_default() {
        let payload = serde_json::json!({"port": 8765});
        let response = dispatch("fast_probe_port", &payload);
        // Port 8765 likely unavailable in test env, but host defaults to 127.0.0.1.
        let parsed: serde_json::Value = serde_json::from_str(&response).expect("parse");
        assert_eq!(parsed["host"], "127.0.0.1");
    }

    #[test]
    fn dispatch_fast_tail_log_missing_path() {
        let payload = serde_json::json!({});
        let response = dispatch("fast_tail_log", &payload);
        assert!(response.contains("missing path"));
    }

    #[test]
    fn dispatch_fast_dir_size_missing_path() {
        let payload = serde_json::json!({});
        let response = dispatch("fast_dir_size", &payload);
        assert!(response.contains("missing path"));
    }
}