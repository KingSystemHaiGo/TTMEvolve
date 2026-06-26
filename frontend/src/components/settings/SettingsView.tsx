/**
 * SettingsView — 设置页面主视图
 *
 * 借鉴 taptap-maker-plus 的 SettingsView 设计（5 面板 + 诊断日志）。
 * 适配 TTMEvolve 的 LLM Router + portable runtime。
 *
 * 用法：
 *   <SettingsView runtimeInfo={...} onRefresh={...} />
 */

import { useEffect, useState } from "react";
import {
  DeveloperModePanel,
  DeveloperSettings,
  McpRuntimePanel,
  McpSchemaPanel,
  PortableStatus,
  ProjectInfoPanel,
  ProjectInfo,
  RuntimeInfo,
  SchemaSummary,
  WorkbenchCapabilitiesPanel,
} from "./panels";
import { Panel } from "../ui/Panel";
import { Toggle } from "../ui/Toggle";

export interface SettingsViewProps {
  project?: ProjectInfo;
  runtime?: RuntimeInfo;
  schema?: SchemaSummary;
  portable?: PortableStatus;
  developer: DeveloperSettings;
  onDeveloperChange: (next: DeveloperSettings) => void;
  logCount: number;
  onClearLogs?: () => void;
  onRefresh?: () => void;
}

export function SettingsView(props: SettingsViewProps) {
  const {
    project,
    runtime,
    schema,
    portable,
    developer,
    onDeveloperChange,
    logCount,
    onClearLogs,
    onRefresh,
  } = props;

  const [themeMode, setThemeMode] = useState<"light" | "dark">(
    () =>
      (typeof document !== "undefined" &&
        (document.documentElement.getAttribute("data-theme") as
          | "light"
          | "dark")) ||
      "light"
  );

  // Sync state when the theme attribute changes (e.g. via ThemeToggle).
  useEffect(() => {
    if (typeof document === "undefined") return;
    const target = document.documentElement;
    const observer = new MutationObserver(() => {
      const next = target.getAttribute("data-theme") as "light" | "dark";
      if (next && next !== themeMode) {
        setThemeMode(next);
      }
    });
    observer.observe(target, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, [themeMode]);

  const toggleTheme = () => {
    const next = themeMode === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("ttmevolve.theme", next);
    } catch {
      // ignore
    }
    setThemeMode(next);
  };

  return (
    <section
      style={{
        flex: 1,
        minHeight: 0,
        overflowY: "auto",
        padding: "var(--space-5) var(--space-6)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-4)",
        backgroundColor: "var(--surface-app)",
      }}
    >
      {/* Header */}
      <header
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <div>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: "var(--font-size-xs)",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              color: "var(--color-text-subtle)",
              marginBottom: 4,
            }}
          >
            设置
          </span>
          <h1
            style={{
              margin: 0,
              fontSize: "var(--font-size-xl)",
              fontWeight: 700,
              color: "var(--color-text)",
            }}
          >
            运行与绑定状态
          </h1>
        </div>
        {onRefresh && (
          <button
            onClick={onRefresh}
            style={{
              padding: "6px 14px",
              borderRadius: "var(--radius-control)",
              border: "1px solid var(--color-border)",
              background: "var(--surface-raised)",
              color: "var(--color-text)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            ↻ 刷新
          </button>
        )}
      </header>

      {/* Theme toggle panel */}
      <Panel title="外观" icon="🎨">
        <Toggle
          checked={themeMode === "dark"}
          onChange={toggleTheme}
          label={themeMode === "dark" ? "暗色模式" : "亮色模式"}
          description={`点击切换到${themeMode === "dark" ? "亮色" : "暗色"}主题；选择会持久化到 localStorage。`}
        />
      </Panel>

      {/* 5 panels grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: "var(--space-4)",
        }}
      >
        <ProjectInfoPanel project={project} />
        <McpRuntimePanel runtime={runtime} />
        <McpSchemaPanel schema={schema} />
        <WorkbenchCapabilitiesPanel portable={portable} />
        <DeveloperModePanel
          settings={developer}
          onToggle={onDeveloperChange}
          logCount={logCount}
          onClearLogs={onClearLogs}
        />
      </div>

      {/* Runtime Error */}
      {runtime?.lastError && (
        <Panel title="运行错误" icon="⚠">
          <pre
            style={{
              margin: 0,
              padding: "var(--space-3)",
              background: "var(--surface-muted)",
              border: "1px solid var(--color-error)",
              borderRadius: "var(--radius-control)",
              color: "var(--color-error)",
              fontSize: "var(--font-size-xs)",
              fontFamily: "var(--font-mono)",
              overflow: "auto",
              maxHeight: 240,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {runtime.lastError}
          </pre>
        </Panel>
      )}
    </section>
  );
}
