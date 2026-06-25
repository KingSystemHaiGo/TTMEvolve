//! Python backend process manager.
//!
//! Owns the lifecycle of the embedded Python FastAPI server:
//!   - detect portable runtime (./portable/python/) first, fall back to PATH
//!   - spawn the server with a deterministic port scan
//!   - stream stdout/stderr to a rotating log file
//!   - expose start/stop/status/health helpers to the Tauri command layer

use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

const SERVER_HOST: &str = "127.0.0.1";
const DEFAULT_PORT: u16 = 8765;
const PORT_SCAN_LIMIT: u16 = 40;
const HEALTH_TIMEOUT_SECONDS: u64 = 30;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

#[derive(Clone, Debug, PartialEq)]
pub enum ServerStatus {
    Idle,
    Starting,
    Running { port: u16, pid: u32 },
    Error(String),
}

#[derive(Clone, Debug)]
pub struct ServerLaunchInfo {
    pub port: u16,
    pub instance_token: String,
    pub launched_at: u128,
}

pub struct ServerManager {
    child: Arc<Mutex<Option<Child>>>,
    launch: Arc<Mutex<Option<ServerLaunchInfo>>>,
    log_path: PathBuf,
    project_root: PathBuf,
}

impl ServerManager {
    pub fn new(project_root: PathBuf, log_path: PathBuf) -> Self {
        Self {
            child: Arc::new(Mutex::new(None)),
            launch: Arc::new(Mutex::new(None)),
            log_path,
            project_root,
        }
    }

    pub fn status(&self) -> ServerStatus {
        let mut guard = self.child.lock().expect("server child lock poisoned");
        match guard.as_mut() {
            None => ServerStatus::Idle,
            Some(child) => match child.try_wait() {
                Ok(Some(_status)) => {
                    // process exited; drop the handle so future start() works
                    *guard = None;
                    ServerStatus::Idle
                }
                Ok(None) => {
                    let launch = self.launch.lock().expect("launch lock poisoned");
                    if let Some(info) = launch.as_ref() {
                        let pid = child.id();
                        ServerStatus::Running {
                            port: info.port,
                            pid,
                        }
                    } else {
                        ServerStatus::Starting
                    }
                }
                Err(err) => ServerStatus::Error(err.to_string()),
            },
        }
    }

    pub fn stop(&self) -> Result<(), String> {
        let mut guard = self.child.lock().expect("server child lock poisoned");
        if let Some(child) = guard.as_mut() {
            #[cfg(windows)]
            {
                let _ = child.kill();
            }
            #[cfg(not(windows))]
            {
                let _ = child.kill();
            }
        }
        *guard = None;
        Ok(())
    }

    pub fn start(&self) -> Result<u16, String> {
        {
            let guard = self.child.lock().expect("server child lock poisoned");
            if guard.is_some() {
                if let Some(info) = self.launch.lock().expect("launch lock poisoned").as_ref() {
                    return Ok(info.port);
                }
            }
        }

        let port = find_available_local_port(SERVER_HOST, DEFAULT_PORT, PORT_SCAN_LIMIT)
            .ok_or_else(|| format!("Unable to find available port from {DEFAULT_PORT}"))?;

        let instance_token = make_instance_token();
        let python_path = resolve_python(&self.project_root);
        let entry_script = self.project_root.join("main.py");

        let (stdout, stderr) = self.open_log_handles()?;
        let mut cmd = Command::new(&python_path);
        cmd.current_dir(&self.project_root)
            .arg(&entry_script)
            .arg("--embedded")
            .arg("--host")
            .arg(SERVER_HOST)
            .arg("--port")
            .arg(port.to_string())
            .env("TTM_EMBEDDED", "1")
            .env("TTM_INSTANCE_TOKEN", &instance_token)
            .env("TTM_PROJECT_ROOT", &self.project_root)
            .env("TTM_PORT", port.to_string())
            .env("PYTHONUNBUFFERED", "1")
            .stdout(Stdio::from(stdout))
            .stderr(Stdio::from(stderr));

        #[cfg(windows)]
        {
            cmd.creation_flags(CREATE_NO_WINDOW);
        }

        let child = cmd
            .spawn()
            .map_err(|err| format!("Failed to spawn Python backend: {err}"))?;
        let pid = child.id();
        *self.child.lock().expect("server child lock poisoned") = Some(child);
        *self.launch.lock().expect("launch lock poisoned") = Some(ServerLaunchInfo {
            port,
            instance_token,
            launched_at: now_millis(),
        });

        // Wait for /health to respond before returning.
        let deadline = std::time::Instant::now() + Duration::from_secs(HEALTH_TIMEOUT_SECONDS);
        while std::time::Instant::now() < deadline {
            if probe_health(port) {
                return Ok(port);
            }
            thread::sleep(Duration::from_millis(200));
        }
        Ok(port)
    }
}

fn resolve_python(project_root: &Path) -> PathBuf {
    let portable = project_root.join("portable").join("python");
    let candidates = if cfg!(windows) {
        vec![
            portable.join("python.exe"),
            portable.join("Scripts").join("python.exe"),
            PathBuf::from(".venv").join("Scripts").join("python.exe"),
        ]
    } else {
        vec![
            portable.join("bin").join("python3"),
            portable.join("bin").join("python"),
            PathBuf::from(".venv").join("bin").join("python3"),
        ]
    };
    for candidate in candidates {
        if candidate.exists() {
            return candidate;
        }
    }
    PathBuf::from(if cfg!(windows) { "python" } else { "python3" })
}

fn find_available_local_port(host: &str, start: u16, limit: u16) -> Option<u16> {
    for offset in 0..=limit {
        let port = start + offset;
        if port_available(host, port) {
            return Some(port);
        }
    }
    None
}

fn port_available(host: &str, port: u16) -> bool {
    TcpListener::bind((host, port)).is_ok()
}

fn probe_health(port: u16) -> bool {
    let addr = format!("{SERVER_HOST}:{port}");
    addr.to_socket_addrs()
        .ok()
        .and_then(|mut addrs| addrs.next())
        .and_then(|sockaddr| TcpStream::connect_timeout(&sockaddr, Duration::from_millis(200)).ok())
        .is_some()
}

fn make_instance_token() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("ttm-{nanos:x}")
}

fn now_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

impl ServerManager {
    fn open_log_handles(&self) -> Result<(Stdio, Stdio), String> {
        if let Some(parent) = self.log_path.parent() {
            fs::create_dir_all(parent).map_err(|err| err.to_string())?;
        }
        let stdout: File = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.log_path)
            .map_err(|err| err.to_string())?;
        let stderr: File = stdout
            .try_clone()
            .map_err(|err| err.to_string())?;
        Ok((Stdio::from(stdout), Stdio::from(stderr)))
    }
}

/// Append a diagnostic line to the desktop log file. Used by lib.rs during
/// early startup before the ServerManager is constructed.
pub fn append_desktop_log(log_path: &Path, line: &str) -> std::io::Result<()> {
    if let Some(parent) = log_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut file = OpenOptions::new().create(true).append(true).open(log_path)?;
    let timestamp = now_millis();
    writeln!(file, "[{timestamp}] {line}")?;
    file.flush()
}

/// Read the last N lines of a log file (used by tauri::command diagnostics).
pub fn tail_log(log_path: &Path, lines: usize) -> std::io::Result<Vec<String>> {
    let content = fs::read_to_string(log_path).unwrap_or_default();
    let buffer: Vec<&str> = content.lines().collect();
    let start = buffer.len().saturating_sub(lines);
    Ok(buffer[start..].iter().map(|s| s.to_string()).collect())
}

/// Convenience helper used by lib.rs to peek at the embedded log file.
pub fn read_log_tail(log_path: &Path) -> String {
    tail_log(log_path, 200).unwrap_or_default().join("\n")
}