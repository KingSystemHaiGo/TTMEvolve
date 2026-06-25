/**
 * Toggle — 开关组件
 *
 * Settings 页面使用：开发者模式、F12 拦截、故障转移等开关。
 */

import React from "react";

interface ToggleProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  label?: React.ReactNode;
  description?: React.ReactNode;
}

export function Toggle({ checked, onChange, disabled, label, description }: ToggleProps) {
  const trackStyle: React.CSSProperties = {
    width: 44,
    height: 24,
    borderRadius: "var(--radius-pill)",
    border: `1px solid ${checked ? "var(--color-brand)" : "var(--color-border)"}`,
    backgroundColor: checked ? "var(--color-brand)" : "var(--surface-muted)",
    position: "relative",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.5 : 1,
    transition: "background-color 120ms ease, border-color 120ms ease",
    flexShrink: 0,
  };
  const thumbStyle: React.CSSProperties = {
    width: 18,
    height: 18,
    borderRadius: "50%",
    backgroundColor: "#FFFFFF",
    position: "absolute",
    top: 2,
    left: checked ? 22 : 2,
    transition: "left 120ms ease",
    boxShadow: "var(--shadow-button)",
  };
  const containerStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    padding: "var(--space-2) var(--space-3)",
    borderRadius: "var(--radius-control)",
    cursor: disabled ? "not-allowed" : "pointer",
  };
  const labelStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    minWidth: 0,
  };
  const titleStyle: React.CSSProperties = {
    fontSize: "var(--font-size-sm)",
    fontWeight: 600,
    color: "var(--color-text)",
  };
  const descStyle: React.CSSProperties = {
    fontSize: "var(--font-size-xs)",
    color: "var(--color-text-muted)",
  };

  return (
    <div
      role="switch"
      aria-checked={checked}
      tabIndex={disabled ? -1 : 0}
      style={containerStyle}
      onClick={() => !disabled && onChange(!checked)}
      onKeyDown={(event) => {
        if (disabled) return;
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          onChange(!checked);
        }
      }}
    >
      {(label || description) && (
        <div style={labelStyle}>
          {label && <span style={titleStyle}>{label}</span>}
          {description && <span style={descStyle}>{description}</span>}
        </div>
      )}
      <div style={trackStyle}>
        <div style={thumbStyle} />
      </div>
    </div>
  );
}