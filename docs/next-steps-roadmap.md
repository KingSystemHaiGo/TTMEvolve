# TTMEvolve 後續工作路線圖

> 生成時間: 2026-06-25
> 當前版本: v0.4.5 → 邁向 v0.5.0（Maker Self-Healing）

---

## ✅ 已完成的工作

### Maker MCP 全通路

| 項目 | 狀態 |
|------|------|
| `server/maker_faults.py` — 14 種故障類型，7 層分類 | ✅ 已建立 |
| `learning/knowledge_seeds.py` → 45+ 條知識種子（原 10 條） | ✅ 已大幅擴充 |
| `agent/agent.py` — 集成 `seed_knowledge_base()` | ✅ 已修改 |
| `server/maker_setup.py` — 集成 `build_maker_fault_analysis()` | ✅ 已修改 |
| `server/app_server.py` — `/maker/repair` 端點 | ✅ 已新增 |
| `scripts/one_click_fix_maker.py` — 獨立一鍵修復腳本 | ✅ 已建立並驗證通過 |
| `scripts/verify_maker_mcp_full_path.py` — 全通路驗證腳本 | ✅ 已建立並驗證通過 |
| 空白創世遊戲拉取到 `D:\本地开发测试` | ✅ 已完成 |
| Maker MCP 全通路 8/8 檢查通過 | ✅ 已驗證 |

### 引擎知識萃取

| 項目 | 狀態 |
|------|------|
| Maker MCP Guide 知識提取（初始化、Git 策略、故障恢復、升級） | ✅ 已完成 |
| UrhoX Lua 引擎知識提取（Core API、UI、物理、相機陷阱） | ✅ 已完成 |
| 知識寫入 TTMEvolve 記憶系統 | ✅ 已完成 |
| 知識種子擴充（Maker MCP Guide、UrhoX Engine、Coding Agent 模式） | ✅ 已完成 |

### Git 狀態

待提交文件:
- 修改: `agent/agent.py`, `core/runtime_contract.py`, `server/app_server.py`, `server/maker_setup.py`, `tests/test_maker_setup.py`
- 新增: `learning/knowledge_seeds.py`, `server/maker_faults.py`, `tests/test_knowledge_seeds.py`, `scripts/one_click_fix_maker.py`, `scripts/verify_maker_mcp_full_path.py`

---

## 📋 後續工作（按優先級排序）

### Phase 1: 代碼清理與第一次發布 🔜 下一步馬上做

- [ ] 審閱所有新文件代碼品質，確保 docstring 一致
- [ ] 更新版本號到 `v0.5.0`
- [ ] 撰寫發布說明 `docs/releases/v0.5.0-maker-self-healing.md`
- [ ] 執行 `git add` + `git commit -m "v0.5.0: Maker MCP self-healing, knowledge seeds expansion"`
- [ ] 建立 tag `v0.5.0`
- [ ] 推送到 `KingSystemHaiGo/TTMEvolve`

### Phase 2: 剩餘知識整合

- [ ] 讀取更多 `engine-docs/` 內容（physics-2d, audio, input, network, graphics）
- [ ] 讀取 `urhox-libs/` 核心庫源碼萃取 API 知識
- [ ] 讀取 `AGENTS.md`（45KB）萃取 Maker 項目開發規範
- [ ] 將 `engine-docs/` 中的範例代碼轉化為知識庫條目
- [ ] 建立 `learning/maker_templates.py` 遊戲模板

### Phase 2: Coding Agent 框架提升

- [x] `core/hooks.py` — pre_session / post_session hooks 已加入
- [x] `core/repair.py` — 指數退避重試（FAULT_MAX_RETRIES + _compute_backoff + jitter）
- [x] `learning/skill_generator.py` — 技能生成後自動觸發跨生態導出
- [x] `ecosystem/opencode_adapter.py` — opencode 適配器（新建）
- [ ] `/loop` 循環執行模式
- [ ] `spawn_subagent()` 工具（Codex 並行子代理）
- [ ] TTMEvolve 內部工具支持條件 hook 觸發器

### Phase 3: 知識整合（持續）

- [x] 已讀取 engine-docs/ 核心知識（gotchas, API, UI, physics, camera）
- [ ] 讀取 `urhox-libs/` 核心庫源碼
- [ ] 讀取 `AGENTS.md`（45KB）完整內容
- [ ] 建立 `learning/maker_templates.py` 遊戲模板
- [ ] 補全 engine-docs/audio, engine-docs/network, engine-docs/graphics

### Phase 4: Maker MCP 深度自修復

- [ ] MCP 子進程看門狗（crash 後自動重啟）
- [ ] 遠端 MCP 版本兼容性檢查
- [ ] `batch_generate_images`/`edit_image` 遠端 500 的回退策略
- [ ] MCP 連接歷史趨勢跟蹤
- [ ] 長時間任務進度推送

---

## 關鍵檢查點

```bash
# Maker MCP 一鍵診斷
python scripts/one_click_fix_maker.py [--fix]

# Maker MCP 全通路驗證
python scripts/verify_maker_mcp_full_path.py

# 知識庫種子測試
python -m pytest tests/test_knowledge_seeds.py -v
```

---

## 🔗 相關文件

- Maker 項目: `D:\本地开发测试` (project_id: `5daf0266-822a-471c-8c43-b92f1d20d5e7`)
- Maker MCP Guide: `C:\Users\WXT\AppData\Local\npm-cache\_npx\...\taptap-maker-local\SKILL.md`
- 引擎文檔: `D:\本地开发测试\engine-docs\`
- Lua 範例: `D:\本地开发测试\examples\`
- ATMEvolve 配置: `D:\CC\TTMEvolve\config.json`

---

> **開發者**: 灰語 & 嗒啦啦
> **核心原則**: TTMEvolve 是主體 — Maker MCP 是能力，Coding Agent 是方法，知識庫是大腦。
