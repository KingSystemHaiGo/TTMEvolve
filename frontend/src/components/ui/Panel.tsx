/**
 * Panel — 通用面板容器
 *
 * 带标题 + 图标的卡片式面板，Settings 页面复用。
 */

import React from "react";

interface PanelProps {
  title?: React.ReactNode;
  icon?: React.ReactNode;
  children: React.ReactNode;
  actions?: React.ReactNode;
  style?: React.CSSProperties;
}

export function Panel({ title, icon, children, actions, style }: PanelProps) {
  return (
    <section
      style={{
        backgroundColor: "var(--surface-panel)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-large)",
        boxShadow: "var(--shadow-panel)",
        overflow: "hidden",
        ...style,
      }}
    >
      {(title || icon || actions) && (
        <header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            padding: "var(--space-3) var(--space-4)",
            borderBottom: "1px solid var(--color-border-soft)",
            backgroundColor: "var(--surface-raised)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
            {icon && (
              <span
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: "var(--radius-control)",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  backgroundColor: "var(--color-brand-soft)",
                  color: "var(--color-brand-strong)",
                  fontSize: 14,
                  flexShrink: 0,
                }}
              >
                {icon}
              </span>
            )}
            {title && (
              <h2
                style={{
                  margin: 0,
                  fontSize: "var(--font-size-sm)",
                  fontWeight: 700,
                  color: "var(--color-text)",
                }}
              >
                {title}
              </h2>
            )}
          </div>
          {actions && <div>{actions}</div>}
        </header>
      )}
      <div style={{ padding: "var(--space-3)" }}>{children}</div>
    </section>
  );
}