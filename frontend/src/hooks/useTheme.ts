/**
 * useTheme — 主题切换 hook
 *
 * - localStorage 持久化用户偏好
 * - 系统主题检测（prefers-color-scheme）
 * - 设置 <html data-theme="..."> 属性
 */

import { useEffect, useState, useCallback } from "react";

export type ThemeMode = "light" | "dark" | "system";

const STORAGE_KEY = "ttmevolve.theme";

function readStoredTheme(): ThemeMode {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === "light" || value === "dark" || value === "system") {
      return value;
    }
  } catch {
    // localStorage unavailable (SSR, restricted context)
  }
  return "system";
}

function systemPrefersDark(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function resolveTheme(mode: ThemeMode): "light" | "dark" {
  if (mode === "system") {
    return systemPrefersDark() ? "dark" : "light";
  }
  return mode;
}

function applyTheme(resolved: "light" | "dark") {
  if (typeof document === "undefined") {
    return;
  }
  document.documentElement.setAttribute("data-theme", resolved);
}

export interface UseThemeResult {
  /** Current mode (may be "system") */
  mode: ThemeMode;
  /** Currently resolved theme ("light" | "dark") */
  resolved: "light" | "dark";
  setMode: (mode: ThemeMode) => void;
  toggle: () => void;
}

export function useTheme(): UseThemeResult {
  const [mode, setModeState] = useState<ThemeMode>(() => readStoredTheme());
  const [systemDark, setSystemDark] = useState<boolean>(() => systemPrefersDark());

  const resolved = resolveTheme(mode);

  // Apply the theme on mount and whenever mode/system changes.
  useEffect(() => {
    applyTheme(resolved);
  }, [resolved]);

  // Track system theme changes when mode is "system".
  useEffect(() => {
    if (mode !== "system" || typeof window === "undefined" || !window.matchMedia) {
      return;
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (event: MediaQueryListEvent) => {
      setSystemDark(event.matches);
    };
    media.addEventListener("change", handler);
    return () => media.removeEventListener("change", handler);
  }, [mode]);

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore
    }
  }, []);

  const toggle = useCallback(() => {
    const next = resolved === "dark" ? "light" : "dark";
    setMode(next);
  }, [resolved, setMode]);

  // Recompute systemDark on demand to keep `resolved` reactive.
  if (mode === "system") {
    const sysResolved = systemDark ? "dark" : "light";
    if (sysResolved !== resolved) {
      // schedule re-render via state
      setTimeout(() => applyTheme(sysResolved), 0);
    }
  }

  return { mode, resolved, setMode, toggle };
}