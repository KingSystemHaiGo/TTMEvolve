"""
server/session_store.py — SQLite 会话持久化

所有会话元数据与 SSE 事件写入 SQLite，支持：
- UI 刷新/重连后回放历史事件
- 服务端重启后读取会话列表与最终结果
- 按时间顺序追加事件（append-only）

注意：当前版本不持久化 ReActLoop 的运行时状态，
因此服务端重启后只能查看已完成会话的历史，无法继续执行中断中的会话。
"""

from __future__ import annotations
import contextlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional


class SessionStore:
    """基于 SQLite 的会话与事件持久化存储。"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    @contextlib.contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    provider TEXT,
                    profile TEXT,
                    status TEXT DEFAULT 'running',
                    result_json TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_events_session
                    ON events(session_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_sessions_status
                    ON sessions(status, updated_at);
                """
            )
            self._ensure_event_column(conn, "source", "TEXT")
            self._ensure_event_column(conn, "meta_json", "TEXT")

    def _ensure_event_column(self, conn: sqlite3.Connection, name: str, column_type: str) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(events)").fetchall()
        }
        if name not in columns:
            conn.execute(f"ALTER TABLE events ADD COLUMN {name} {column_type}")

    def create_session(
        self,
        session_id: str,
        task: str,
        provider: Optional[str] = None,
        profile: Optional[str] = None,
    ) -> None:
        now = time.time()
        with self._lock, self._conn() as conn:
            conn.execute(
                "DELETE FROM events WHERE session_id = ?",
                (session_id,),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions
                (session_id, task, provider, profile, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, task, provider, profile, "running", now, now),
            )

    def append_event(
        self,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any],
        meta: Optional[Dict[str, Any]] = None,
        source: str = "",
    ) -> None:
        now = time.time()
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO events (session_id, event_type, payload_json, created_at, source, meta_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    event_type,
                    json.dumps(payload, ensure_ascii=False),
                    now,
                    source,
                    json.dumps(meta or {}, ensure_ascii=False),
                ),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_session(row)

    def list_sessions(
        self,
        limit: int = 100,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock, self._conn() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM sessions
                    WHERE status = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM sessions
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [self._row_to_session(row) for row in rows]

    def get_events(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                """
                SELECT event_type, payload_json, created_at, source, meta_json
                FROM events
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            ).fetchall()
            return [
                {
                    "type": row["event_type"],
                    "session_id": session_id,
                    "payload": json.loads(row["payload_json"]),
                    "source": row["source"] or "",
                    "meta": json.loads(row["meta_json"]) if row["meta_json"] else {},
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def get_commit_history(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Return commit-state related events in chronological order."""
        history: List[Dict[str, Any]] = []
        for event in self.get_events(session_id):
            event_type = event.get("type")
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            observation = payload.get("observation") if isinstance(payload.get("observation"), dict) else {}
            if event_type == "observation":
                observation = payload.get("observation") if isinstance(payload.get("observation"), dict) else {}
            elif event_type == "commit_reconcile":
                observation = observation or {}
            else:
                continue

            idempotency_key = (
                observation.get("idempotency_key")
                or payload.get("idempotency_key")
            )
            has_commit_field = (
                "committed" in observation
                or "committed" in payload
                or bool(idempotency_key)
                or bool(observation.get("reconcile_status"))
                or bool(payload.get("status"))
            )
            if not has_commit_field:
                continue

            committed = observation.get("committed") if "committed" in observation else payload.get("committed")
            history.append({
                "step": payload.get("iteration"),
                "event_type": event_type,
                "tool": payload.get("tool") or observation.get("tool"),
                "path": observation.get("path"),
                "idempotency_key": idempotency_key,
                "committed": committed,
                "reconcile_status": observation.get("reconcile_status") or payload.get("status"),
                "remote_lookup_tool": observation.get("remote_lookup_tool"),
                "observed_at": observation.get("observed_at"),
                "timestamp": event.get("created_at"),
            })

        if limit > 0:
            return history[-limit:]
        return history

    def get_context_sync_history(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Return compact shared-context snapshots in chronological order."""
        history: List[Dict[str, Any]] = []
        for event in self.get_events(session_id):
            if event.get("type") != "context_sync":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
            checkpoint = (
                snapshot.get("continuation_checkpoint")
                if isinstance(snapshot.get("continuation_checkpoint"), dict)
                else {}
            )
            history.append({
                "step": payload.get("iteration"),
                "reason": payload.get("reason"),
                "revision": payload.get("revision"),
                "changed": payload.get("changed"),
                "signature": payload.get("signature"),
                "previous_signature": payload.get("previous_signature"),
                "diff_keys": payload.get("diff_keys") if isinstance(payload.get("diff_keys"), list) else [],
                "snapshot": snapshot,
                "last_tool": snapshot.get("last_tool"),
                "plan_verdict": (snapshot.get("plan_validation") or {}).get("verdict")
                    if isinstance(snapshot.get("plan_validation"), dict)
                    else None,
                "goal_overall": (snapshot.get("goal_checklist") or {}).get("overall")
                    if isinstance(snapshot.get("goal_checklist"), dict)
                    else None,
                "workspace_profile": snapshot.get("workspace_profile") or checkpoint.get("workspace_profile"),
                "continuation_checkpoint": checkpoint,
                "resume_ready": checkpoint.get("resume_ready"),
                "resume_mode": checkpoint.get("resume_mode"),
                "open_plan_count": len(checkpoint.get("open_plan_steps") or [])
                    if isinstance(checkpoint.get("open_plan_steps"), list)
                    else 0,
                "artifact_count": snapshot.get("artifact_count", 0),
                "timestamp": event.get("created_at"),
            })

        if limit > 0:
            return history[-limit:]
        return history

    def get_runtime_metrics_history(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Return compact runtime diagnostics without replaying the full SSE stream."""
        history: List[Dict[str, Any]] = []
        for event in self.get_events(session_id):
            event_type = event.get("type")
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            metric: Optional[Dict[str, Any]] = None

            if event_type == "latency":
                metric = {
                    "kind": "latency",
                    "phase": payload.get("phase"),
                    "iteration": payload.get("iteration"),
                    "elapsed_ms": payload.get("elapsed_ms"),
                    "tool": payload.get("tool"),
                    "ok": payload.get("ok"),
                    "source_phase": payload.get("source_phase"),
                }
            elif event_type == "llm_usage":
                metric = {
                    "kind": "llm_usage",
                    "phase": payload.get("phase"),
                    "provider": payload.get("provider"),
                    "mode": payload.get("mode"),
                    "prompt_tokens": payload.get("prompt_tokens"),
                    "completion_tokens": payload.get("completion_tokens"),
                    "total_tokens": payload.get("total_tokens"),
                    "generate_ms": payload.get("generate_ms"),
                    "tokens_per_sec": payload.get("tokens_per_sec"),
                    "error_type": payload.get("error_type"),
                }
            elif event_type == "tool_selection":
                stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
                tools = payload.get("tools") if isinstance(payload.get("tools"), list) else []
                metric = {
                    "kind": "tool_selection",
                    "phase": payload.get("phase") or "think",
                    "iteration": payload.get("iteration"),
                    "candidate_count": stats.get("candidate_count"),
                    "selected_count": stats.get("selected_count") or len(tools),
                    "ranking_ms": stats.get("ranking_ms"),
                    "cache_hit": stats.get("cache_hit"),
                    "cache_size": stats.get("cache_size"),
                    "tools": [
                        {
                            "name": tool.get("name"),
                            "source": tool.get("source"),
                        }
                        for tool in tools[:8]
                        if isinstance(tool, dict)
                    ],
                }
            elif event_type == "context_budget":
                metric = {
                    "kind": "context_budget",
                    "phase": payload.get("phase"),
                    "iteration": payload.get("iteration"),
                    "token_count": payload.get("token_count"),
                    "n_ctx": payload.get("n_ctx"),
                    "token_usage_ratio": payload.get("token_usage_ratio"),
                    "context_window_ratio": payload.get("context_window_ratio"),
                    "compression_applied": payload.get("compression_applied"),
                    "dropped_parts": payload.get("dropped_parts"),
                    "truncated_chars": payload.get("truncated_chars"),
                    "token_cache_hits": payload.get("token_cache_hits"),
                    "token_cache_misses": payload.get("token_cache_misses"),
                    "token_cache_size": payload.get("token_cache_size"),
                    "agents_md_hits": payload.get("agents_md_hits"),
                    "cold_recall_hits": payload.get("cold_recall_hits"),
                    "agents_md_ms": payload.get("agents_md_ms"),
                    "cold_recall_ms": payload.get("cold_recall_ms"),
                    "context_build_ms": payload.get("context_build_ms"),
                }

            if metric is None:
                continue
            metric["timestamp"] = event.get("created_at")
            history.append(metric)

        if limit > 0:
            return history[-limit:]
        return history

    def get_learning_history(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Return learning-layer state transitions in chronological order."""
        history: List[Dict[str, Any]] = []
        for event in self.get_events(session_id):
            if event.get("type") != "layer":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            if payload.get("layer") != "learning":
                continue
            event_name = str(payload.get("event") or "")
            if not event_name.startswith("learning."):
                continue
            history.append({
                "event": event_name,
                "state": payload.get("state"),
                "detail": payload.get("detail"),
                "source_layer": payload.get("source_layer"),
                "target_layer": payload.get("target_layer"),
                "cause": payload.get("cause"),
                "metrics": payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
                "timestamp": event.get("created_at"),
            })

        if limit > 0:
            return history[-limit:]
        return history

    def get_layer_history(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Return compact three-layer communication events in chronological order."""
        history: List[Dict[str, Any]] = []
        for event in self.get_events(session_id):
            if event.get("type") != "layer":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            history.append({
                "schema_version": payload.get("schema_version"),
                "layer": payload.get("layer"),
                "state": payload.get("state"),
                "event": payload.get("event"),
                "detail": payload.get("detail"),
                "source_layer": payload.get("source_layer"),
                "target_layer": payload.get("target_layer"),
                "correlation_id": payload.get("correlation_id"),
                "cause": payload.get("cause"),
                "metrics": payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
                "timestamp": event.get("created_at"),
            })

        if limit > 0:
            return history[-limit:]
        return history

    def get_maker_guard_history(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Return compact Maker first-action guard decisions in chronological order."""
        history: List[Dict[str, Any]] = []
        for event in self.get_events(session_id):
            if event.get("type") != "maker_briefing_guard":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            selected_template = payload.get("selected_template") if isinstance(payload.get("selected_template"), dict) else {}
            history.append({
                "step": payload.get("iteration"),
                "decision": payload.get("decision"),
                "tool": payload.get("tool"),
                "reason": payload.get("reason"),
                "authority": payload.get("authority"),
                "selected_template": {
                    "id": selected_template.get("id"),
                    "status": selected_template.get("status"),
                },
                "allowed_tools": payload.get("allowed_tools") if isinstance(payload.get("allowed_tools"), list) else [],
                "suggested_tools": payload.get("suggested_tools") if isinstance(payload.get("suggested_tools"), list) else [],
                "recommended_first_action": payload.get("recommended_first_action"),
                "recommended_endpoint": payload.get("recommended_endpoint"),
                "timestamp": event.get("created_at"),
            })

        if limit > 0:
            return history[-limit:]
        return history

    def get_llm_probe_history(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Return compact LLM provider probe diagnostics in chronological order."""
        history: List[Dict[str, Any]] = []
        for event in self.get_events(session_id):
            if event.get("type") != "llm_probe":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            stats = payload.get("last_call_stats") if isinstance(payload.get("last_call_stats"), dict) else {}
            history.append({
                "status": payload.get("status"),
                "ok": payload.get("ok"),
                "provider": payload.get("provider"),
                "runtime_kind": payload.get("runtime_kind"),
                "llm_class": payload.get("llm_class"),
                "model": payload.get("model"),
                "base_url": payload.get("base_url"),
                "elapsed_ms": payload.get("elapsed_ms"),
                "output_preview": payload.get("output_preview"),
                "endpoint": stats.get("endpoint"),
                "http_status": stats.get("http_status"),
                "total_tokens": stats.get("total_tokens"),
                "generate_ms": stats.get("generate_ms"),
                "error_type": stats.get("error_type"),
                "error": payload.get("error"),
                "timestamp": event.get("created_at"),
            })

        if limit > 0:
            return history[-limit:]
        return history

    def mark_done(
        self,
        session_id: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        now = time.time()
        status = "error" if error else "done"
        result_json = json.dumps(result, ensure_ascii=False) if result else None
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET status = ?, result_json = ?, error = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (status, result_json, error, now, session_id),
            )

    def mark_cancelled(
        self,
        session_id: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = time.time()
        result_json = json.dumps(result, ensure_ascii=False) if result else None
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET status = ?, result_json = ?, error = ?, updated_at = ?
                WHERE session_id = ?
                """,
                ("canceled", result_json, None, now, session_id),
            )

    def _row_to_session(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "session_id": row["session_id"],
            "task": row["task"],
            "provider": row["provider"],
            "profile": row["profile"],
            "status": row["status"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
