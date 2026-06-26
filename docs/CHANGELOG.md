# TTMEvolv2 CHANGELOG

> 所有 v1.0+ 的 release notes。

---

## v1.4.0（计划中）— Release 准备

- [ ] 完整 release checklist
- [ ] 时间戳同步
- [ ] 文档汇总

## v1.3.0 — 国际化（2026-06-26）

**新增：**
- `core/i18n.py` — 轻量 i18n 模块（线程安全）
- `i18n/en-US.json` + `i18n/zh-CN.json` — 63 翻译字符串
- `tests/test_i18n.py` — 31 个测试覆盖

**覆盖：**
- app / settings / agent / maker / intent / tools / updater / error / startup

## v1.2.0 — E2E 测试（2026-06-26）

**新增：**
- `tests/test_e2e_runtime.py` — 19 个 E2E 测试
- 直接调用 public API，避开 HTTP server boot
- 覆盖所有关键公共路径

## v1.1.0 — 代码签名（2026-06-26）

**新增：**
- `scripts/build_portable/build_portable.py` — 编排器
- `scripts/build_portable/build_sign_windows.py` — signtool 包装
- `scripts/build_portable/build_sign_macos.py` — codesign + notarytool
- `scripts/build_portable/build_sign_linux.py` — GPG + manifest
- `scripts/build_portable/build_publish.py` — GitHub Releases 上传
- `tests/test_build_portable_sign.py` — 18 个测试覆盖

## v1.0.0 — 自动更新集成（2026-06-26）

**新增：**
- tauri-plugin-updater 依赖
- `src-tauri/src/updater.rs` — Rust updater 模块（12 个测试）
- `core/updater_client.py` — Python 客户端（23 个测试）
- GitHub Releases 源配置
- Prerelease 语义正确处理

## v0.9.0 — 跨平台（2026-06-26）

**新增：**
- Tauri 三平台 targets（Windows / Linux / macOS）
- `start-tauri.bat` / `start-tauri.sh` 三模式（gui / cli / headless）
- Bundle metadata（category / publisher / license / homepage）
- `tests/test_start_scripts.py` — 14 个测试

## v0.8.0 — Tauri 自动桥接（2026-06-26）

**新增：**
- `BridgeHandle` + `start_background` — 桥接生命周期
- `bridge_status` Tauri command
- 关闭时同时停止 Python 后端和桥接
- `tests/test_tauri_lifecycle.py` — 12 个测试

## v0.7.3 — Rust ↔ Python HTTP 桥接（2026-06-26）

**新增：**
- `src-tauri/src/fast_ops_http.rs` — HTTP 桥接服务器
  - std::net::TcpListener + per-connection thread
  - POST /fast_ops/{command}
  - /health endpoint
  - 9 个 Rust 单元测试
- `core/fast_ops_client.py` 更新 — `_invoke_rust()` HTTP 调用
- `tests/test_fast_ops_http.py` — 14 个 Python 测试

## v0.7.2 — Rust 内核替换热路径（2026-06-26）

**新增：**
- `src-tauri/src/fast_ops.rs` — Rust 热路径
  - `probe_port` / `find_available_port` / `port_available`
  - `tail_log` / `dir_size` / `list_dir`
  - `format_bytes`（IEC）
  - 7 个 Rust 单元测试
- `core/fast_ops_client.py` — Python 客户端 + 自动 fallback
- `tests/test_fast_ops_client.py` — 13 个 Python 测试

## v0.7.1 — Electron 删除准备（2026-06-26）

**新增：**
- `scripts/remove-electron.py` — 迁移脚本（dry-run 默认）
- `tests/test_remove_electron.py` — 17 个只读测试
- `docs/v0.7.1-electron-removal.md` — 完整迁移指南

## v0.7.0 — 完整 Windows 桌面应用（2026-06-26）

**架构变更：**
- 桌面壳：Electron → Tauri 2.x（Rust + WebView2）
- LLM 策略：本地模型 → 全面云端（LLMRouter + 9 Provider + 故障转移）
- 包体积：~450MB → ~200MB（-60%）

**新增 6 个里程碑：**
- M1a：内嵌环境包 + LLM 路由层（云端）
- M1b：主题系统 + Settings 5 面板
- M2：后端 API（/api/settings/*）
- M3：Tauri 壳 + Rust 服务管理
- M4：portable 启动 + 离线测试
- M5：性能优化 + 测试 + 发布（tag 推送）

**测试：** 192/192 通过

---

## 旧版本历史

详见 `docs/releases/` 目录下的 v0.5.0、v0.6.0 等独立 release notes。