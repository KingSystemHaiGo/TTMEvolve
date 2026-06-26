/**
 * Settings 5 面板
 *
 * 1. 当前项目（ProjectInfoPanel）
 * 2. MCP Runtime（McpRuntimePanel）
 * 3. 真实 MCP Schema（McpSchemaPanel）
 * 4. 本地工作台能力（WorkbenchCapabilitiesPanel）
 * 5. 开发者模式（DeveloperModePanel）
 *
 * 借鉴 taptap-maker-plus 的 SettingsView 设计。
 */

import { Panel } from "../ui/Panel";
import { Toggle } from "../ui/Toggle";
import { SettingRow } from "./SettingRow";

// ---------- 类型定义 ----------

export interface ProjectInfo {
  name: string;
  rootPath: string;
  makerProjectId: string;
  configPath: string;
}

export interface RuntimeInfo {
  status: string;
  processId?: number;
  cwd: string;
  toolsListUpdatedAt?: string;
  launchCommand: string;
  lastError?: string;
}

export interface SchemaSummary {
  total: number;
  categories: Record<string, number>;
  formSource: string;
}

export interface PortableStatus {
  python: { embedded: boolean; version?: string; path: string };
  node: { embedded: boolean; version?: string; path: string };
  makerMcp: { embedded: boolean; path: string };
}

export interface DeveloperSettings {
  f12Enabled: boolean;
  verboseLogs: boolean;
}

// ---------- 1. 当前项目 ----------

export function ProjectInfoPanel({ project }: { project?: ProjectInfo }) {
  return (
    <Panel title="当前项目" icon="📁">
      <SettingRow label="项目名" value={project?.name ?? "-"} />
      <SettingRow label="项目路径" value={project?.rootPath ?? "-"} mono />
      <SettingRow label="Maker 项目 ID" value={project?.makerProjectId ?? "-"} mono />
      <SettingRow label="配置文件" value={project?.configPath ?? "-"} mono />
    </Panel>
  );
}

// ---------- 2. MCP Runtime ----------

export function McpRuntimePanel({ runtime }: { runtime?: RuntimeInfo }) {
  const status = runtime?.status ?? "idle";
  const statusColor =
    status === "running"
      ? "var(--color-success)"
      : status === "error"
      ? "var(--color-error)"
      : "var(--color-text-subtle)";

  return (
    <Panel title="MCP 运行状态" icon="⚡">
      <SettingRow
        label="状态"
        value={
          <span style={{ color: statusColor, fontWeight: 700 }}>
            ● {runtimeStatusLabel(status)}
          </span>
        }
      />
      <SettingRow
        label="进程 ID"
        value={runtime?.processId ? String(runtime.processId) : "-"}
      />
      <SettingRow label="运行目录" value={runtime?.cwd ?? "-"} mono />
      <SettingRow
        label="工具列表更新时间"
        value={runtime?.toolsListUpdatedAt ?? "-"}
      />
      <SettingRow label="启动命令" value={runtime?.launchCommand ?? "-"} mono />
      {runtime?.lastError && (
        <SettingRow
          label="最近错误"
          value={
            <span style={{ color: "var(--color-error)" }}>
              {runtime.lastError}
            </span>
          }
        />
      )}
    </Panel>
  );
}

function runtimeStatusLabel(status: string): string {
  switch (status) {
    case "running":
      return "运行中";
    case "error":
      return "异常";
    case "idle":
      return "空闲";
    default:
      return status || "未知";
  }
}

// ---------- 3. 真实 MCP Schema ----------

export function McpSchemaPanel({ schema }: { schema?: SchemaSummary }) {
  return (
    <Panel title="MCP 工具结构" icon="🧩">
      <SettingRow label="工具总数" value={schema?.total ?? 0} />
      {schema &&
        Object.entries(schema.categories).map(([category, count]) => (
          <SettingRow
            key={category}
            label={category}
            value={`${count} 个工具`}
          />
        ))}
      <SettingRow label="表单来源" value={schema?.formSource ?? "-"} />
    </Panel>
  );
}

// ---------- 4. 本地工作台能力 ----------

export function WorkbenchCapabilitiesPanel({
  portable,
}: {
  portable?: PortableStatus;
}) {
  const checks: Array<{ label: string; ok: boolean; detail?: string }> = [
    {
      label: "内嵌 Python",
      ok: portable?.python.embedded ?? false,
      detail: portable?.python.version
        ? `${portable.python.version} · ${portable.python.path}`
        : portable?.python.path,
    },
    {
      label: "内嵌 Node",
      ok: portable?.node.embedded ?? false,
      detail: portable?.node.version
        ? `${portable.node.version} · ${portable.node.path}`
        : portable?.node.path,
    },
    {
      label: "Maker MCP 运行环境",
      ok: portable?.makerMcp.embedded ?? false,
      detail: portable?.makerMcp.path,
    },
    { label: "本地接口", ok: true, detail: "FastAPI / 127.0.0.1:8765" },
    { label: "前端", ok: true, detail: "React + Vite + 自定义主题" },
    { label: "模型路由", ok: true, detail: "云端多供应商 + 故障转移" },
  ];
  return (
    <Panel title="本地工作台能力" icon="🛠">
      {checks.map(({ label, ok, detail }) => (
        <SettingRow
          key={label}
          label={label}
          value={
            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span
                style={{
                  color: ok ? "var(--color-success)" : "var(--color-error)",
                  fontSize: 14,
                }}
              >
                {ok ? "✓" : "✗"}
              </span>
              <span style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-xs)" }}>
                {detail ?? ""}
              </span>
            </span>
          }
        />
      ))}
    </Panel>
  );
}

// ---------- 5. 开发者模式 ----------

export interface DeveloperModePanelProps {
  settings: DeveloperSettings;
  onToggle: (next: DeveloperSettings) => void;
  logCount: number;
  onClearLogs?: () => void;
}

export function DeveloperModePanel({
  settings,
  onToggle,
  logCount,
  onClearLogs,
}: DeveloperModePanelProps) {
  return (
    <Panel title="开发者模式" icon="🐞">
      <Toggle
        checked={settings.f12Enabled}
        onChange={(next) => onToggle({ ...settings, f12Enabled: next })}
        label="允许 F12 打开 DevTools"
        description="关闭后会拦截 F12 / Ctrl+Shift+I；仅用于本地调试。"
      />
      <Toggle
        checked={settings.verboseLogs}
        onChange={(next) => onToggle({ ...settings, verboseLogs: next })}
        label="详细日志"
        description="记录 ReAct / Hook / LLM Router 的完整事件流。"
      />
      <SettingRow label="前端诊断日志" value={`${logCount} 条`} />
      <div style={{ display: "flex", gap: 8, padding: "var(--space-2) var(--space-3)" }}>
        <button
          onClick={onClearLogs}
          style={{
            padding: "4px 10px",
            fontSize: "var(--font-size-xs)",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--color-border)",
            background: "var(--surface-raised)",
            color: "var(--color-text-muted)",
            cursor: "pointer",
          }}
        >
          清空日志
        </button>
      </div>
    </Panel>
  );
}
