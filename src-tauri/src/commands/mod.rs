//! Tauri command layer — exposed to the webview via tauri.invoke.

use std::sync::Arc;

use serde::Serialize;
use tauri::{AppHandle, Manager, Runtime, State, Window};

use crate::server_manager::{ServerManager, ServerStatus};

#[derive(Serialize)]
pub struct ServerStatusDto {
    pub status: String,
    pub port: Option<u16>,
    pub pid: Option<u32>,
}

impl From<&ServerStatus> for ServerStatusDto {
    fn from(status: &ServerStatus) -> Self {
        match status {
            ServerStatus::Idle => Self { status: "idle".into(), port: None, pid: None },
            ServerStatus::Starting => Self { status: "starting".into(), port: None, pid: None },
            ServerStatus::Running { port, pid } => Self {
                status: "running".into(),
                port: Some(*port),
                pid: Some(*pid),
            },
            ServerStatus::Error(err) => Self {
                status: format!("error: {err}"),
                port: None,
                pid: None,
            },
        }
    }
}

#[tauri::command]
pub fn server_status<R: Runtime>(
    _app: AppHandle<R>,
    manager: State<'_, Arc<ServerManager>>,
) -> ServerStatusDto {
    ServerStatusDto::from(&manager.status())
}

#[tauri::command]
pub fn server_start<R: Runtime>(
    _app: AppHandle<R>,
    manager: State<'_, Arc<ServerManager>>,
) -> Result<ServerStatusDto, String> {
    manager.start()?;
    Ok(ServerStatusDto::from(&manager.status()))
}

#[tauri::command]
pub fn server_stop<R: Runtime>(
    _app: AppHandle<R>,
    manager: State<'_, Arc<ServerManager>>,
) -> Result<(), String> {
    manager.stop()
}

#[tauri::command]
pub fn open_devtools<R: Runtime>(window: Window<R>) -> Result<(), String> {
    #[cfg(debug_assertions)]
    {
        window.open_devtools();
    }
    let _ = window; // suppress unused warning in release builds
    Ok(())
}

pub fn register<R: Runtime, T: tauri::Builder<R>>(
    builder: T,
) -> T {
    builder.invoke_handler(tauri::generate_handler![
        server_status,
        server_start,
        server_stop,
        open_devtools,
    ])
}