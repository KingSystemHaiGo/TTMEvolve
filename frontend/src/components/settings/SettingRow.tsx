/**
 * SettingRow — key/value 行
 */

import React from "react";

interface SettingRowProps {
  label: React.ReactNode;
  value: React.ReactNode;
  mono?: boolean;
  hint?: React.ReactNode;
}

export function SettingRow({ label, value, mono, hint }: SettingRowProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: hint ? "flex-start" : "center",
        justifyContent: "space-between",
        gap: 12,
        padding: "var(--space-2) var(--space-3)",
        borderRadius: "var(--radius-control)",
        fontSize: "var(--font-size-xs)",
      }}
    >
      <span
        style={{
          flexShrink: 0,
          fontWeight: 600,
          color: "var(--color-text-subtle)",
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          minWidth: 100,
        }}
      >
        {label}
      </span>
      <div style={{ minWidth: 0, textAlign: "right", flex: 1 }}>
        <strong
          title={typeof value === "string" ? value : undefined}
          style={{
            display: "block",
            minWidth: 0,
            fontSize: "var(--font-size-sm)",
            fontWeight: 600,
            color: "var(--color-text)",
            fontFamily: mono ? "var(--font-mono)" : undefined,
            wordBreak: mono ? "break-all" : undefined,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: mono ? "normal" : "nowrap",
          }}
        >
          {value}
        </strong>
        {hint && (
          <span
            style={{
              display: "block",
              marginTop: 2,
              fontSize: "var(--font-size-xs)",
              color: "var(--color-text-subtle)",
            }}
          >
            {hint}
          </span>
        )}
      </div>
    </div>
  );
}