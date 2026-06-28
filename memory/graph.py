"""
memory/graph.py - typed-edge graph memory layer (Phase A).

This module sits on top of the existing flat cold memory. It is opt-in
(feature flag ``memory.graph.enabled``, default ``false``) and preserves
the public surface of ``memory.cold.ColdMemory``.

Storage layout (additive, under the existing cold-memory storage root):

    cold_graph_nodes.jsonl       # append-only MemoryNode stream
    cold_graph_edges.jsonl       # append-only MemoryEdge stream
    cold_graph_tombstones.jsonl  # append-only soft deletes
    cold_graph_meta.json         # {version, node_count, edge_count, last_compaction_at}
    graph_edges/                 # optional second VectorIndex namespace for edge glue text

Edge types are a fixed allowlist (see ``EDGE_TYPES``). Unknown edge types
are rejected at write time, not at search time, to keep the graph honest.

Retrieval in Phase A is keyword/encoder fallback. Vector + graph expansion
with the five-factor ranking from ADR-0004 lands in Phase B.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set


GRAPH_FORMAT_VERSION = "memory-graph.v1"

EDGE_TYPES: Set[str] = {
    "references",
    "supersedes",
    "contradicts",
    "supports",
    "caused_by",
    "temporal_next",
    "decomposes_into",
    "similar_to",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MemoryNode:
    id: str
    type: str = "unknown"
    summary: str = ""
    content_ref: str = ""
    workspace_profile: str = "general"
    agent_id: str = "default"
    visibility: str = "private"
    timestamp: float = 0.0
    claim_key: str = ""
    tags: List[str] = field(default_factory=list)
    bayes: Dict[str, float] = field(default_factory=dict)
    soft_deleted: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "MemoryNode":
        """Build a node from a JSON dict, ignoring unknown keys."""
        if not isinstance(raw, dict):
            raise ValueError("MemoryNode.from_dict requires a dict")
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: raw[k] for k in raw if k in known}
        return cls(**clean)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryEdge:
    id: str
    src: str
    dst: str
    type: str
    weight: float = 1.0
    created_at: float = 0.0
    evidence_refs: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "MemoryEdge":
        if not isinstance(raw, dict):
            raise ValueError("MemoryEdge.from_dict requires a dict")
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: raw[k] for k in raw if k in known}
        return cls(**clean)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# MemoryGraph
# ---------------------------------------------------------------------------

class MemoryGraph:
    """Typed-edge graph memory layer.

    Parameters
    ----------
    storage_path : Path
        Directory where the four JSONL/JSON files live. Created if missing.
    vector_index : Optional
        Reserved for Phase B (second VectorIndex namespace for edge glue
        text). Phase A does not consume it.
    config : Dict
        ``max_edges_per_node`` (int, default 64),
        ``expand_hops`` (int, default 1),
        ``edge_index_enabled`` (bool, default False).
    encoder : Optional[Callable]
        Optional encoder used by the keyword fallback path. Accepts a
        list of strings and returns a numpy array of shape (n, dim).
        When None, the fallback uses a character-hash encoder.
    """

    def __init__(
        self,
        storage_path: Path,
        vector_index: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        encoder: Optional[Callable[[List[str]], Any]] = None,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        cfg = dict(config or {})
        self.max_edges_per_node = int(cfg.get("max_edges_per_node", 64))
        self.expand_hops = int(cfg.get("expand_hops", 1))
        self.edge_index_enabled = bool(cfg.get("edge_index_enabled", False))
        self._vector_index = vector_index
        self._encoder = encoder

        self._nodes_path = self.storage_path / "cold_graph_nodes.jsonl"
        self._edges_path = self.storage_path / "cold_graph_edges.jsonl"
        self._tombstones_path = self.storage_path / "cold_graph_tombstones.jsonl"
        self._meta_path = self.storage_path / "cold_graph_meta.json"

        self._nodes: Dict[str, MemoryNode] = {}
        self._tombstones: Dict[str, Dict[str, Any]] = {}
        # adjacency: src -> dst set, and dst -> src set (undirected lookups)
        self._out_edges: Dict[str, Set[str]] = {}
        self._in_edges: Dict[str, Set[str]] = {}
        # typed adjacency: src -> (edge_type, dst) set
        self._out_edges_typed: Dict[str, Set[tuple]] = {}

        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert_node(self, node: MemoryNode) -> None:
        """Insert or replace a node by id."""
        if not node.id:
            raise ValueError("MemoryNode.id is required")
        if not node.timestamp:
            node.timestamp = time.time()
        self._nodes[node.id] = node
        # If this id was previously tombstoned, drop the tombstone (restore)
        self._tombstones.pop(node.id, None)
        self._append_jsonl(self._nodes_path, node.to_dict())
        self._update_meta()

    def get_node(self, node_id: str, *, include_soft_deleted: bool = False) -> Optional[MemoryNode]:
        """Return a live (non-tombstoned) node, or None.

        When ``include_soft_deleted`` is True, return the node even if it
        is tombstoned (the ``soft_deleted`` field stays True on the
        returned object). This lets callers distinguish "not in graph"
        from "tombstoned in graph" without reaching into private state.
        """
        node = self._nodes.get(node_id)
        if node is None:
            return None
        if node_id in self._tombstones and not include_soft_deleted:
            return None
        return node

    def soft_delete_node(self, node_id: str, *, reason: str = "manual") -> None:
        """Mark a node as soft-deleted; it stays in JSONL for restore."""
        if node_id not in self._nodes:
            return
        self._nodes[node_id].soft_deleted = True
        self._tombstones[node_id] = {
            "id": node_id,
            "reason": reason,
            "deleted_at": time.time(),
        }
        self._append_jsonl(self._tombstones_path, self._tombstones[node_id])
        # Drop in-memory adjacency for the deleted node
        for dst in self._out_edges.pop(node_id, set()):
            self._in_edges.get(dst, set()).discard(node_id)
        for src in self._in_edges.pop(node_id, set()):
            self._out_edges.get(src, set()).discard(node_id)
        self._out_edges_typed.pop(node_id, None)
        self._update_meta()

    def restore_node(self, node_id: str) -> bool:
        """Undo a soft delete. Returns True if the node was tombstoned."""
        if node_id not in self._tombstones:
            return False
        if node_id in self._nodes:
            self._nodes[node_id].soft_deleted = False
        self._tombstones.pop(node_id, None)
        # Record the restore in the tombstone log so re-replay can drop it
        self._append_jsonl(
            self._tombstones_path,
            {"id": node_id, "reason": "restored", "deleted_at": time.time()},
        )
        return True

    def add_edge(self, edge: MemoryEdge) -> None:
        if edge.type not in EDGE_TYPES:
            raise ValueError(
                f"Unknown edge type: {edge.type!r}. Allowed: {sorted(EDGE_TYPES)}"
            )
        if edge.src not in self._nodes:
            raise ValueError(f"src node not found: {edge.src}")
        if edge.dst not in self._nodes:
            raise ValueError(f"dst node not found: {edge.dst}")
        # Enforce max outgoing edges per node
        existing = self._out_edges.get(edge.src, set())
        if edge.dst not in existing and len(existing) >= self.max_edges_per_node:
            raise ValueError(
                f"max_edges_per_node ({self.max_edges_per_node}) exceeded for {edge.src}"
            )
        if not edge.id:
            edge.id = f"e-{uuid.uuid4().hex[:12]}"
        if not edge.created_at:
            edge.created_at = time.time()
        self._out_edges.setdefault(edge.src, set()).add(edge.dst)
        self._in_edges.setdefault(edge.dst, set()).add(edge.src)
        self._out_edges_typed.setdefault(edge.src, set()).add((edge.type, edge.dst))
        self._append_jsonl(self._edges_path, edge.to_dict())
        self._update_meta()

    def remove_edge(self, src: str, dst: str, type: str) -> bool:
        """Remove a specific (src, dst, type) edge if present."""
        if src not in self._out_edges or dst not in self._out_edges[src]:
            return False
        self._out_edges[src].discard(dst)
        self._in_edges.get(dst, set()).discard(src)
        # Filter typed adjacency
        typed = self._out_edges_typed.get(src, set())
        typed.discard((type, dst))
        return True

    def neighbors(
        self,
        node_id: str,
        edge_types: Optional[Iterable[str]] = None,
        max_hops: Optional[int] = None,
    ) -> Set[str]:
        """Return reachable node ids up to ``max_hops`` (default: ``expand_hops``).

        Uses a visited set to break cycles. ``edge_types`` filters by edge
        type at the first hop only — multi-hop expansion follows any edge.
        """
        if node_id not in self._nodes or node_id in self._tombstones:
            return set()
        max_h = self.expand_hops if max_hops is None else int(max_hops)
        allowed_first = set(edge_types) if edge_types is not None else None
        visited: Set[str] = set()
        frontier: Set[str] = {node_id}
        for _ in range(max_h):
            next_frontier: Set[str] = set()
            for src in frontier:
                candidates: Iterable[tuple]
                if src == node_id and allowed_first is not None:
                    candidates = {
                        (t, d) for (t, d) in self._out_edges_typed.get(src, set()) if t in allowed_first
                    }
                else:
                    candidates = {
                        (t, d) for (t, d) in self._out_edges_typed.get(src, set())
                    }
                for _, dst in candidates:
                    if dst in visited or dst in frontier or dst == node_id:
                        continue
                    if dst in self._tombstones:
                        continue
                    next_frontier.add(dst)
            if not next_frontier:
                break
            visited.update(next_frontier)
            frontier = next_frontier
        # Drop tombstoned targets and self
        return {n for n in visited if n not in self._tombstones and n != node_id}

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        expand_hops: Optional[int] = None,
        edge_type_filter: Optional[Iterable[str]] = None,
        workspace_profile: Optional[str] = None,
        include_soft_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return ranked candidates for ``query``.

        Phase A implementation: keyword/encoder fallback ranked by
        substring hit count. Phase B adds the five-factor vector+posterior
        ranking from ADR-0004. ``include_soft_deleted`` is False by default.
        """
        candidates = self._keyword_candidates(query, top_k=top_k * 4)
        # Profile filter
        if workspace_profile:
            candidates = [
                c for c in candidates
                if c["workspace_profile"] == workspace_profile
                or c["workspace_profile"] == "general"
            ]
        if not include_soft_deleted:
            candidates = [c for c in candidates if not c.get("soft_deleted")]
        # Re-rank: token overlap count, then posterior (if any)
        query_tokens = _tokenize(query)
        scored: List[tuple] = []
        for cand in candidates:
            text_tokens = _tokenize(cand.get("summary", "")) | set(_tokenize(cand.get("type", "")))
            overlap = len(query_tokens & text_tokens)
            posterior = float(cand.get("bayes", {}).get("posterior", 0.5)) if isinstance(cand.get("bayes"), dict) else 0.5
            scored.append((overlap + 0.1 * posterior, cand))
        scored.sort(key=lambda x: x[0], reverse=True)
        # Strip the score from the result; caller doesn't need it.
        return [c for _, c in scored[:top_k]]

    # ------------------------------------------------------------------
    # Internal: persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        # Load nodes
        if self._nodes_path.exists():
            for line in self._nodes_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    node = MemoryNode.from_dict(raw)
                except Exception:
                    continue
                # If the file was already written, the latest occurrence wins.
                # soft_deleted is sticky until restore.
                if node.id in self._tombstones:
                    self._nodes[node.id] = node
                    continue
                self._nodes[node.id] = node
        # Load tombstones (last write wins; "restored" wins over earlier delete)
        if self._tombstones_path.exists():
            for line in self._tombstones_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except Exception:
                    continue
                if not isinstance(raw, dict) or "id" not in raw:
                    continue
                if raw.get("reason") == "restored":
                    self._tombstones.pop(raw["id"], None)
                else:
                    self._tombstones[raw["id"]] = raw
                    if raw["id"] in self._nodes:
                        self._nodes[raw["id"]].soft_deleted = True
        # Load edges
        if self._edges_path.exists():
            for line in self._edges_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    edge = MemoryEdge.from_dict(raw)
                except Exception:
                    continue
                if edge.src not in self._nodes or edge.dst not in self._nodes:
                    continue
                if edge.type not in EDGE_TYPES:
                    continue
                self._out_edges.setdefault(edge.src, set()).add(edge.dst)
                self._in_edges.setdefault(edge.dst, set()).add(edge.src)
                self._out_edges_typed.setdefault(edge.src, set()).add((edge.type, edge.dst))
        # Drop any node that is tombstoned from in-memory search index
        for tid in list(self._tombstones.keys()):
            if tid in self._nodes:
                self._nodes[tid].soft_deleted = True
        # Initial meta
        if not self._meta_path.exists():
            self._update_meta()

    def _append_jsonl(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _update_meta(self) -> None:
        meta = {
            "version": GRAPH_FORMAT_VERSION,
            "node_count": sum(1 for n in self._nodes.values() if n.id not in self._tombstones),
            "edge_count": sum(len(dsts) for dsts in self._out_edges.values()),
            "tombstone_count": len(self._tombstones),
            "last_compaction_at": 0.0,
        }
        self._meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Internal: keyword/encoder fallback
    # ------------------------------------------------------------------

    def _keyword_candidates(self, query: str, *, top_k: int) -> List[Dict[str, Any]]:
        query_tokens = _tokenize(query)
        if not query_tokens:
            # Empty query → all live nodes, in insertion-ish order
            return [n.to_dict() for n in self._nodes.values() if n.id not in self._tombstones][:top_k]
        scored: List[tuple] = []
        for node in self._nodes.values():
            if node.id in self._tombstones:
                continue
            text = (node.summary or "") + " " + (node.type or "")
            text_tokens = _tokenize(text)
            overlap = len(query_tokens & text_tokens)
            if overlap > 0:
                scored.append((overlap, node))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [n.to_dict() for _, n in scored[:top_k]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> Set[str]:
    """Naive tokenizer: lowercase + word-split for English, char-split for CJK.

    Phase A is intentionally simple. Phase B can swap in the same encoder
    used by the second VectorIndex namespace.
    """
    out: Set[str] = set()
    s = (text or "").lower()
    if not s:
        return out
    # English words
    for word in s.split():
        word = word.strip(".,:;!?()[]{}\"'`")
        if len(word) >= 2:
            out.add(word)
    # CJK characters
    for ch in s:
        if "一" <= ch <= "鿿":
            out.add(ch)
    return out
