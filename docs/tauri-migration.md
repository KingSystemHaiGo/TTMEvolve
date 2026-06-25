# TTMEvolve Tauri 迁移指南

> v0.7.0 桌面壳从 Electron 迁移到 Tauri 2.x。
> 本文描述架构、构建步骤、运行流程、迁移路径。

---

## 1. 为什么迁移到 Tauri

| 维度 | Electron（v0.6） | Tauri 2.x（v0.7） |
|------|-----------------|-------------------|
| 安装包 | ~120MB | ~80MB |
| 后台内存 | ~150MB | ~80MB |
| 启动时间 | ~5s | ~2s |
| 安全模型 | Node.js 内嵌 | Rust 内核 + WebView2 |
| 系统调用 | Node.js API | Rust 直接调用 |

---

## 2. 项目结构

```
TTMEvolve/
├── src-tauri/                ← 新增：Rust 桌面壳
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── build.rs
│   ├── capabilities/
│   │   └── default.json
│   ├── icons/                ← 应用图标
│   └── src/
│       ├── main.rs           ← 入口
│       ├── lib.rs            ← Tauri Builder
│       ├── server_manager.rs ← Python 进程管理
│       └── commands/
│           └── mod.rs        ← tauri::command 列表
├── frontend/                 ← 不变：React + Vite
├── electron/                 ← v0.7.1 deprecated
└── start-tauri.bat           ← Windows 启动（优先内嵌环境）
```

---

## 3. 启动流程

```
1. Tauri 启动 Rust 主进程（main.rs → lib.rs::run）
2. resolve_project_root() — 优先 resource_dir，回退 current_exe parent
3. resolve_log_path() — app_log_dir/desktop.log
4. ServerManager::start():
   a. 探测 8765 端口（若占用，scan 到 8765+40）
   b. resolve_python():
      - portable/python/python.exe 或 portable/python/bin/python3
      - .venv/Scripts/python.exe 或 .venv/bin/python3
      - 系统 PATH 上的 python
   c. spawn(`python main.py --embedded --host 127.0.0.1 --port <port>`)
   d. 等待 /health 返回（30s 超时）
5. Tauri 加载 WebView2 → frontend/dist/index.html
6. 前端通过 tauri.invoke('server_status') 等命令与 Rust 通信
```

---

## 4. Tauri 命令列表

| 命令 | 用途 |
|------|------|
| `server_status` | 获取后端状态（idle / starting / running / error） |
| `server_start` | 启动 Python 后端（如未启动） |
| `server_stop` | 停止 Python 后端 |
| `open_devtools` | 打开 DevTools（仅 debug 构建） |

前端封装：`frontend/src/lib/tauri.ts`

---

## 5. 构建步骤

### 5.1 前置依赖

| 工具 | 版本 | 用途 |
|------|------|------|
| Rust | 1.77+ | 编译 src-tauri |
| Node.js | 20+ | 构建 frontend |
| Microsoft C++ Build Tools | 最新版 | Rust on Windows |
| WebView2 Runtime | Windows 10/11 自带 | Tauri WebView |

### 5.2 构建命令

```bash
# 1. 安装前端依赖 + 构建
cd frontend
npm install
npm run build
cd ..

# 2. 构建 Tauri 应用（首次较慢，需要编译所有依赖）
cd src-tauri
cargo build --release
cd ..

# 3. 输出位置
# Windows: src-tauri/target/release/ttmevolve.exe
# Linux: src-tauri/target/release/ttmevolve
# macOS: src-tauri/target/release/ttmevolve
```

### 5.3 打包为安装包

```bash
cd src-tauri
cargo tauri build
# 输出：src-tauri/target/release/bundle/
#   nsis/  → TTMEvolve_0.7.0_x64-setup.exe
#   msi/   → TTMEvolve_0.7.0_x64_en-US.msi
```

---

## 6. 内嵌资源

`tauri.conf.json` 中 `bundle.resources` 指定哪些文件被打包到安装包：

```json
"resources": {
  "../portable": "portable",
  "../main.py": "main.py",
  "../core": "core",
  "../agent": "agent",
  "../llm": "llm",
  "../learning": "learning",
  "../server": "server",
  "../memory": "memory",
  "../ecosystem": "ecosystem",
  "../cli": "cli",
  "../config.json": "config.json",
  "../start.bat": "start.bat",
  "../start.sh": "start.sh"
}
```

安装后这些文件位于 `<install>/resources/` 下。

---

## 7. 启动脚本优先级

`start-tauri.bat` / `start-tauri.sh` 的 Python 解析顺序：

1. `portable/python/python.exe`（或 `bin/python3`）— 内嵌
2. `.venv/Scripts/python.exe`（或 `bin/python3`）— 虚拟环境
3. 系统 PATH 上的 `python`（或 `python3`）

**未安装任何依赖**也能运行（前提是 portable/ 已打包好）。

---

## 8. Electron 退出路径

| 版本 | Electron | Tauri |
|------|----------|-------|
| v0.6.0 | ✅ 主用 | ❌ |
| v0.7.0 | ⚠️ 兼容 | ✅ 主用 |
| v0.7.1 | ⚠️ deprecated | ✅ 主用 |
| v0.8.0 | ❌ 删除 | ✅ 主用 |

---

## 9. 调试

```bash
# 前端热重载
cd frontend && npm run dev

# Tauri dev 模式（自动加载 devUrl）
cd src-tauri && cargo tauri dev

# 查看后端日志
tail -f <app_log_dir>/desktop.log
```

---

## 10. 已知问题

1. **首次 cargo build 慢**：Rust 编译 + 数百个依赖
2. **WebView2 仅 Windows**：Linux/macOS 用 webkit2gtk / webkit
3. **图标**：占位图标，需要替换为品牌图标

---

> 制定者：灰语 & 嗒啦啦
> 来源：taptap-maker-plus 参考
> 原则：性能 / 后台占用 / 后续升级