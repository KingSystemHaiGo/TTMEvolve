//! Tauri command layer — exposed to the webview via tauri.invoke.

use std::process::Command;
use std::sync::Arc;

use serde::{Deserialize, Serialize};
use tauri::{
    AppHandle, LogicalPosition, LogicalSize, Manager, Position, Rect, Runtime, Size, State, Window,
};

use crate::fast_ops::{self, DirSizeResult, FileEntry, LogTail, PortProbeResult};
use crate::server_manager::{ServerManager, ServerStatus};

const MAKER_PREVIEW_LABEL: &str = "maker-preview";
const MAKER_PREVIEW_DEFAULT_URL: &str = "https://maker.taptap.cn/";

#[derive(Serialize)]
pub struct ServerStatusDto {
    pub status: String,
    pub port: Option<u16>,
    pub pid: Option<u32>,
}

#[derive(Serialize)]
pub struct BridgeStatusDto {
    pub version: &'static str,
    pub host: String,
    pub port: u16,
    pub running: bool,
}

#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PreviewBoundsDto {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

impl From<&ServerStatus> for ServerStatusDto {
    fn from(status: &ServerStatus) -> Self {
        match status {
            ServerStatus::Idle => Self {
                status: "idle".into(),
                port: None,
                pid: None,
            },
            ServerStatus::Starting => Self {
                status: "starting".into(),
                port: None,
                pid: None,
            },
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
    #[cfg(feature = "devtools")]
    {
        window.open_devtools();
    }
    let _ = window; // suppress unused warning in release builds
    Ok(())
}

#[tauri::command]
pub fn window_minimize<R: Runtime>(window: Window<R>) -> Result<(), String> {
    window.minimize().map_err(|err| err.to_string())
}

#[tauri::command]
pub fn window_toggle_maximize<R: Runtime>(window: Window<R>) -> Result<(), String> {
    if window.is_maximized().map_err(|err| err.to_string())? {
        window.unmaximize().map_err(|err| err.to_string())
    } else {
        window.maximize().map_err(|err| err.to_string())
    }
}

#[tauri::command]
pub fn window_close<R: Runtime>(window: Window<R>) -> Result<(), String> {
    window.close().map_err(|err| err.to_string())
}

fn is_allowed_external_url(url: &str) -> bool {
    let trimmed = url.trim();
    if trimmed.chars().any(|ch| ch.is_control()) {
        return false;
    }
    trimmed.starts_with("https://") || trimmed.starts_with("http://")
}

fn parse_preview_url(url: Option<String>) -> Result<tauri::Url, String> {
    let raw = url
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or(MAKER_PREVIEW_DEFAULT_URL);
    if !is_allowed_external_url(raw) {
        return Err("preview URL must use http or https".to_string());
    }
    raw.parse::<tauri::Url>()
        .map_err(|err| format!("invalid preview URL: {err}"))
}

fn validated_preview_bounds(bounds: PreviewBoundsDto) -> Result<Rect, String> {
    if !bounds.x.is_finite()
        || !bounds.y.is_finite()
        || !bounds.width.is_finite()
        || !bounds.height.is_finite()
    {
        return Err("preview bounds must be finite numbers".to_string());
    }

    let width = bounds.width.max(1.0);
    let height = bounds.height.max(1.0);
    Ok(Rect {
        position: Position::Logical(LogicalPosition::new(bounds.x.max(0.0), bounds.y.max(0.0))),
        size: Size::Logical(LogicalSize::new(width, height)),
    })
}

#[tauri::command]
pub fn open_external_url(url: String) -> Result<(), String> {
    let url = url.trim().to_string();
    if !is_allowed_external_url(&url) {
        return Err("only http/https URLs can be opened externally".to_string());
    }

    #[cfg(target_os = "windows")]
    let mut command = {
        let mut command = Command::new("rundll32");
        command.args(["url.dll,FileProtocolHandler", &url]);
        command
    };

    #[cfg(target_os = "macos")]
    let mut command = {
        let mut command = Command::new("open");
        command.arg(&url);
        command
    };

    #[cfg(all(unix, not(target_os = "macos")))]
    let mut command = {
        let mut command = Command::new("xdg-open");
        command.arg(&url);
        command
    };

    command
        .spawn()
        .map(|_| ())
        .map_err(|err| format!("failed to open URL externally: {err}"))
}

#[tauri::command]
pub async fn maker_preview_show<R: Runtime>(
    app: AppHandle<R>,
    window: Window<R>,
    url: Option<String>,
    bounds: PreviewBoundsDto,
) -> Result<(), String> {
    let parsed_url = parse_preview_url(url)?;
    let rect = validated_preview_bounds(bounds)?;

    if let Some(webview) = app.get_webview(MAKER_PREVIEW_LABEL) {
        webview.show().map_err(|err| err.to_string())?;
        webview
            .set_bounds(rect)
            .map_err(|err| format!("failed to resize Maker preview: {err}"))?;
        webview
            .navigate(parsed_url)
            .map_err(|err| format!("failed to navigate Maker preview: {err}"))?;
        return Ok(());
    }

    let builder = tauri::webview::WebviewBuilder::new(
        MAKER_PREVIEW_LABEL,
        tauri::WebviewUrl::External(parsed_url),
    );
    let position = LogicalPosition::new(
        match rect.position {
            Position::Logical(value) => value.x,
            Position::Physical(value) => value.x as f64,
        },
        match rect.position {
            Position::Logical(value) => value.y,
            Position::Physical(value) => value.y as f64,
        },
    );
    let size = LogicalSize::new(
        match rect.size {
            Size::Logical(value) => value.width,
            Size::Physical(value) => value.width as f64,
        },
        match rect.size {
            Size::Logical(value) => value.height,
            Size::Physical(value) => value.height as f64,
        },
    );

    window
        .add_child(builder, position, size)
        .map_err(|err| format!("failed to create Maker preview: {err}"))?;
    Ok(())
}

#[tauri::command]
pub async fn maker_preview_hide<R: Runtime>(app: AppHandle<R>) -> Result<(), String> {
    if let Some(webview) = app.get_webview(MAKER_PREVIEW_LABEL) {
        webview.hide().map_err(|err| err.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub async fn maker_preview_set_bounds<R: Runtime>(
    app: AppHandle<R>,
    bounds: PreviewBoundsDto,
) -> Result<(), String> {
    let Some(webview) = app.get_webview(MAKER_PREVIEW_LABEL) else {
        return Ok(());
    };
    webview
        .set_bounds(validated_preview_bounds(bounds)?)
        .map_err(|err| format!("failed to resize Maker preview: {err}"))
}

#[tauri::command]
pub async fn maker_preview_navigate<R: Runtime>(
    app: AppHandle<R>,
    url: String,
) -> Result<(), String> {
    let parsed_url = parse_preview_url(Some(url))?;
    let Some(webview) = app.get_webview(MAKER_PREVIEW_LABEL) else {
        return Err("Maker preview is not ready".to_string());
    };
    webview
        .navigate(parsed_url)
        .map_err(|err| format!("failed to navigate Maker preview: {err}"))
}

#[tauri::command]
pub async fn maker_preview_reload<R: Runtime>(app: AppHandle<R>) -> Result<(), String> {
    let Some(webview) = app.get_webview(MAKER_PREVIEW_LABEL) else {
        return Ok(());
    };
    webview
        .reload()
        .map_err(|err| format!("failed to reload Maker preview: {err}"))
}

// ---------- fast_ops: hot path commands ----------

#[tauri::command]
pub fn fast_probe_port(host: String, port: u16, timeout_ms: Option<u64>) -> PortProbeResult {
    fast_ops::probe_port(&host, port, timeout_ms.unwrap_or(200))
}

#[tauri::command]
pub fn fast_find_available_port(
    host: String,
    start: u16,
    limit: u16,
    timeout_ms: Option<u64>,
) -> Option<u16> {
    fast_ops::find_available_port(&host, start, limit, timeout_ms.unwrap_or(200))
}

#[tauri::command]
pub fn fast_tail_log(path: String, max_bytes: Option<u64>) -> Result<LogTail, String> {
    fast_ops::tail_log(std::path::Path::new(&path), max_bytes.unwrap_or(262144))
        .map_err(|err| err.to_string())
}

#[tauri::command]
pub fn fast_dir_size(path: String) -> Result<DirSizeResult, String> {
    fast_ops::dir_size(std::path::Path::new(&path)).map_err(|err| err.to_string())
}

#[tauri::command]
pub fn fast_list_dir(path: String) -> Result<Vec<FileEntry>, String> {
    fast_ops::list_dir(std::path::Path::new(&path)).map_err(|err| err.to_string())
}

#[tauri::command]
pub fn fast_format_bytes(bytes: u64) -> String {
    fast_ops::format_bytes(bytes)
}

#[tauri::command]
pub fn bridge_status<R: Runtime>(app: AppHandle<R>) -> BridgeStatusDto {
    let bridge_running = app
        .try_state::<crate::fast_ops_http::BridgeHandle>()
        .map(|handle| handle.is_running())
        .unwrap_or(false);
    BridgeStatusDto {
        version: crate::fast_ops_http::BRIDGE_VERSION,
        host: crate::fast_ops_http::DEFAULT_HOST.to_string(),
        port: crate::fast_ops_http::DEFAULT_PORT,
        running: bridge_running,
    }
}

pub fn register<R: Runtime>(builder: tauri::Builder<R>) -> tauri::Builder<R> {
    builder.invoke_handler(tauri::generate_handler![
        server_status,
        server_start,
        server_stop,
        open_devtools,
        window_minimize,
        window_toggle_maximize,
        window_close,
        open_external_url,
        maker_preview_show,
        maker_preview_hide,
        maker_preview_set_bounds,
        maker_preview_navigate,
        maker_preview_reload,
        fast_probe_port,
        fast_find_available_port,
        fast_tail_log,
        fast_dir_size,
        fast_list_dir,
        fast_format_bytes,
        bridge_status,
    ])
}

#[cfg(test)]
mod tests {
    use super::{is_allowed_external_url, validated_preview_bounds, PreviewBoundsDto};

    #[test]
    fn external_url_validation_allows_http_and_https_only() {
        assert!(is_allowed_external_url("https://maker.taptap.cn/"));
        assert!(is_allowed_external_url("http://127.0.0.1:7345/health"));
        assert!(!is_allowed_external_url("file:///C:/secret.txt"));
        assert!(!is_allowed_external_url("javascript:alert(1)"));
        assert!(!is_allowed_external_url("https://maker.taptap.cn/\ncalc"));
    }

    #[test]
    fn preview_bounds_validation_clamps_to_visible_positive_rect() {
        let rect = validated_preview_bounds(PreviewBoundsDto {
            x: -12.0,
            y: 8.0,
            width: 0.0,
            height: 320.0,
        })
        .unwrap();
        match rect.position {
            tauri::Position::Logical(position) => {
                assert_eq!(position.x, 0.0);
                assert_eq!(position.y, 8.0);
            }
            tauri::Position::Physical(_) => panic!("expected logical position"),
        }
        match rect.size {
            tauri::Size::Logical(size) => {
                assert_eq!(size.width, 1.0);
                assert_eq!(size.height, 320.0);
            }
            tauri::Size::Physical(_) => panic!("expected logical size"),
        }
    }
}
