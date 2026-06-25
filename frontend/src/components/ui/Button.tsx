/**
 * Button — 通用按钮组件
 *
 * 变体：primary / secondary / ghost / outline / danger
 * 尺寸：sm / md / lg
 */

import React from "react";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "ghost"
  | "outline"
  | "danger";
export type ButtonSize = "sm" | "md" | "lg";

interface BaseProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  fullWidth?: boolean;
  icon?: React.ReactNode;
  children?: React.ReactNode;
}

type ButtonProps = BaseProps &
  Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, keyof BaseProps>;

const VARIANT_STYLES: Record<ButtonVariant, React.CSSProperties> = {
  primary: {
    backgroundColor: "var(--color-brand)",
    color: "var(--color-text-inverse)",
    border: "1px solid transparent",
  },
  secondary: {
    backgroundColor: "var(--surface-raised)",
    color: "var(--color-text)",
    border: "1px solid var(--color-border)",
  },
  ghost: {
    backgroundColor: "transparent",
    color: "var(--color-text-muted)",
    border: "1px solid transparent",
  },
  outline: {
    backgroundColor: "transparent",
    color: "var(--color-text)",
    border: "1px solid var(--color-border)",
  },
  danger: {
    backgroundColor: "var(--color-error)",
    color: "#FFFFFF",
    border: "1px solid transparent",
  },
};

const SIZE_STYLES: Record<ButtonSize, React.CSSProperties> = {
  sm: {
    padding: "4px 10px",
    fontSize: "var(--font-size-xs)",
    height: 24,
    borderRadius: "var(--radius-control)",
  },
  md: {
    padding: "6px 14px",
    fontSize: "var(--font-size-sm)",
    height: 32,
    borderRadius: "var(--radius-control)",
  },
  lg: {
    padding: "8px 18px",
    fontSize: "var(--font-size-base)",
    height: 40,
    borderRadius: "var(--radius-control)",
  },
};

export function Button(props: ButtonProps) {
  const {
    variant = "secondary",
    size = "md",
    loading = false,
    fullWidth = false,
    icon,
    children,
    style,
    disabled,
    ...rest
  } = props;

  const isDisabled = disabled || loading;
  const baseStyle: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    cursor: isDisabled ? "not-allowed" : "pointer",
    fontWeight: 600,
    opacity: isDisabled ? 0.5 : 1,
    transition: "background-color 120ms ease, color 120ms ease, border-color 120ms ease",
    width: fullWidth ? "100%" : undefined,
    ...VARIANT_STYLES[variant],
    ...SIZE_STYLES[size],
    ...style,
  };

  return (
    <button
      {...rest}
      disabled={isDisabled}
      style={baseStyle}
      onMouseEnter={(event) => {
        if (isDisabled) return;
        const el = event.currentTarget;
        if (variant === "primary") {
          el.style.backgroundColor = "var(--color-brand-strong)";
        } else if (variant === "ghost") {
          el.style.backgroundColor = "var(--surface-hover)";
        } else if (variant === "outline" || variant === "secondary") {
          el.style.backgroundColor = "var(--surface-hover)";
        }
        rest.onMouseEnter?.(event);
      }}
      onMouseLeave={(event) => {
        const el = event.currentTarget;
        el.style.backgroundColor = VARIANT_STYLES[variant].backgroundColor as string;
        rest.onMouseLeave?.(event);
      }}
    >
      {loading ? <span style={{ opacity: 0.6 }}>…</span> : icon}
      {children}
    </button>
  );
}