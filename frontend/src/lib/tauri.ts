/**
 * Tauri command bridge — typed wrappers around tauri.invoke.
 *
 * When running inside the Tauri shell, calls go through the Rust backend.
 * In a plain browser (dev fallback) the same function names return stubs
 * so the frontend works without a Rust runtime.
 */

export interface ServerStatusDto {
  status: "idle" | "starting" | "running" | "error";
  port: number | null;
  pid: number | null;
  errorMessage?: string;
}

function isTauri(): boolean {
  if (typeof window === "undefined") return false;
  // tauri-apps/api exposes __TAURI_INTERNALS__ at runtime
  return Boolean((window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__);
}

async function invoke<T>(name: string, args?: Record<string, unknown>): Promise<T> {
  if (!isTauri()) {
    throw new Error(`Tauri runtime not available; cannot invoke ${name}`);
  }
  const tauri = await import("@tauri-apps/api/core");
  return tauri.invoke<T>(name, args);
}

export async function getServerStatus(): Promise<ServerStatusDto> {
  if (!isTauri()) {
    return { status: "idle", port: null, pid: null };
  }
  return invoke<ServerStatusDto>("server_status");
}

export async function startServer(): Promise<ServerStatusDto> {
  if (!isTauri()) {
    return { status: "running", port: 8765, pid: null };
  }
  return invoke<ServerStatusDto>("server_start");
}

export async function stopServer(): Promise<void> {
  if (!isTauri()) return;
  await invoke<void>("server_stop");
}

export async function openDevtools(): Promise<void> {
  if (!isTauri()) return;
  await invoke<void>("open_devtools");
}

export async function openExternalUrl(url: string): Promise<void> {
  if (!isTauri()) {
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }
  await invoke<void>("open_external_url", { url });
}

export { isTauri };
