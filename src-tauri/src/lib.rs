//! TTMEvolve Tauri 桌面壳 — 应用入口
//!
//! 启动顺序（v0.8.0）：
//!   1. 探测 8765 端口（Python 后端）
//!   2. 启动 Python 后端子进程（portable/.venv/python.exe main.py）
//!   3. 启动 fast_ops HTTP 桥接（8766 端口，让 Python 调用 Rust 热路径）
//!   4. 等待 /health 返回 200
//!   5. 加载 WebView2 显示 frontend/dist/index.html
//!   6. frontend 通过 tauri.invoke 调用 Rust commands

use std::path::PathBuf;
use std::sync::Arc;

use serde::Serialize;
use tauri::{Manager, RunEvent, WindowEvent};

mod commands;
mod fast_ops;
mod fast_ops_http;
mod server_manager;
mod updater;

use fast_ops_http::{start_background as start_bridge, BridgeConfig, BridgeHandle};
use server_manager::{ServerLaunchInfo, ServerManager, ServerStatus};

#[derive(Clone, Serialize)]
struct DesktopDiagnostics {
    version: &'static str,
    server_status: &'static str,
    server_port: Option<u16>,
    server_pid: Option<u32>,
    instance_token: Option<String>,
    desktop_log_path: String,
    project_root: String,
}

const APP_VERSION: &str = "0.8.0";
const BRIDGE_DEFAULT_HOST: &str = "127.0.0.1";
const BRIDGE_DEFAULT_PORT: u16 = 8766;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::new().build())
        .plugin(tauri_plugin_dialog::init());

    builder = builder.setup(|app| {
        let project_root = resolve_project_root(app)?;
        let log_path = resolve_log_path(app)?;
        let _ = server_manager::append_desktop_log(
            &log_path,
            &format!("TTMEvolve {APP_VERSION} starting in {}", project_root.display()),
        );

        // 1. Start the fast_ops HTTP bridge so the Python backend can call
        //    into Rust hot paths (port scanning, log tail, dir size).
        let bridge_config = BridgeConfig {
            host: BRIDGE_DEFAULT_HOST.to_string(),
            port: BRIDGE_DEFAULT_PORT,
        };
        let bridge_handle: BridgeHandle = match start_bridge(bridge_config) {
            Ok(handle) => {
                let _ = server_manager::append_desktop_log(
                    &log_path,
                    &format!(
                        "fast_ops bridge listening on http://{}:{}",
                        handle.addr.ip(),
                        handle.addr.port()
                    ),
                );
                handle
            }
            Err(err) => {
                let _ = server_manager::append_desktop_log(
                    &log_path,
                    &format!("fast_ops bridge start failed: {err}"),
                );
                eprintln!("[ttmevolve] bridge start failed: {err}");
                // Continue without the bridge — Python fallback still works.
                BridgeHandle {
                    addr: std::net::SocketAddr::from(([0, 0, 0, 0], 0)),
                    stop: Arc::new(std::sync::atomic::AtomicBool::new(true)),
                }
            }
        };

        // 2. Start the Python backend subprocess.
        let manager = ServerManager::new(project_root.clone(), log_path.clone());
        if let Err(err) = manager.start() {
            eprintln!("[ttmevolve] backend start failed: {err}");
            let _ = server_manager::append_desktop_log(
                &log_path,
                &format!("backend start failed: {err}"),
            );
        }

        let manager = Arc::new(manager);
        app.manage(manager.clone());
        app.manage(bridge_handle);

        Ok(())
    });

    builder = commands::register(builder);

    let app = builder
        .build(tauri::generate_context!())
        .expect("failed to build TTMEvolve Tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::WindowEvent {
            label,
            event: WindowEvent::CloseRequested { .. },
            ..
        } = event
        {
            // On window close, stop both the Python backend and the bridge.
            if let Some(manager) = app_handle.try_state::<Arc<ServerManager>>() {
                let _ = manager.stop();
            }
            if let Some(bridge) = app_handle.try_state::<BridgeHandle>() {
                bridge.stop();
            }
            // Suppress unused warning when label is intentionally ignored.
            let _ = label;
        }
    });
}

fn resolve_project_root(app: &tauri::App) -> Result<PathBuf, Box<dyn std::error::Error>> {
    // Use Tauri's resource_dir as the canonical project root when running from
    // a packaged build; otherwise fall back to current_exe parent (dev mode).
    if let Ok(resource) = app.path().resource_dir() {
        return Ok(resource);
    }
    let exe = std::env::current_exe()?;
    let parent = exe.parent().ok_or("current_exe has no parent")?;
    Ok(parent.to_path_buf())
}

fn resolve_log_path(app: &tauri::App) -> Result<PathBuf, Box<dyn std::error::Error>> {
    let dir = app.path().app_log_dir()?;
    Ok(dir.join("desktop.log"))
}

#[allow(dead_code)]
fn diagnostics_from(launch: &Option<ServerLaunchInfo>, status: &ServerStatus, log_path: &str, project_root: &str) -> DesktopDiagnostics {
    let (server_status, server_port, server_pid) = match status {
        ServerStatus::Idle => ("idle".to_string(), None, None),
        ServerStatus::Starting => ("starting".to_string(), None, None),
        ServerStatus::Running { port, pid } => ("running".to_string(), Some(*port), Some(*pid)),
        ServerStatus::Error(_) => ("error".to_string(), None, None),
    };
    DesktopDiagnostics {
        version: APP_VERSION,
        server_status: Box::leak(server_status.into_boxed_str()),
        server_port,
        server_pid,
        instance_token: launch.as_ref().map(|info| info.instance_token.clone()),
        desktop_log_path: log_path.to_string(),
        project_root: project_root.to_string(),
    }
}