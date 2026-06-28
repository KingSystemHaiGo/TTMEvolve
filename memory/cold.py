"""
memory/cold.py — 冷记忆

长期归档：所有轨迹、知识、事件的摘要索引。
使用 JSON 文件作为源文件，向量索引（FAISS + sentence-transformers）作为检索后端，
向量不可用时自动降级为关键词匹配。
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import json
import time

from .vector_index import TextChunk, VectorIndex
from .shared_policy import SharedMemoryPolicy
from .shared_outcome import review_shared_memory_outcome, shared_outcome_summary
from .graph import MemoryEdge, MemoryGraph, MemoryNode
from .bayes import BayesianScorer, BayesianState, occam_score
from typing import Set

_KNOWN_WORKSPACE_PROFILES = {"coding", "docs", "maker", "browser", "general"}
_DEFAULT_PROFILE_POLICIES: Dict[str, Dict[str, Any]] = {
    "general": {"include_general": True, "allow_fallback": False},
    "coding": {"include_general": True, "allow_fallback": True},
    "docs": {"include_general": True, "allow_fallback": True},
    "maker": {"include_general": True, "allow_fallback": True},
    "browser": {"include_general": True, "allow_fallback": True},
}


class ColdMemory:
    """冷记忆：长期归档与语义检索。"""

    def __init__(
        self,
        storage_path: Path,
        vector_index_config: Optional[Dict[str, Any]] = None,
        encoder: Optional[Any] = None,
        graph_config: Optional[Dict[str, Any]] = None,
        bayes_config: Optional[Dict[str, Any]] = None,
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._index_path = self.storage_path / "cold_index.json"
        self._conflicts_path = self.storage_path / "shared_memory_conflicts.json"
        self._index: List[Dict[str, Any]] = []
        self._conflicts: List[Dict[str, Any]] = []

        vi_cfg = vector_index_config or {}
        self._fallback_to_keyword = vi_cfg.get("fallback_to_keyword", True)
        self._profile_policies = _resolve_profile_policies(vi_cfg.get("profile_policies"))
        self._shared_policy_config = vi_cfg.get("shared_memory") if isinstance(vi_cfg.get("shared_memory"), dict) else {}

        # Phase A: typed-edge graph memory (off by default)
        self._graph_config = dict(graph_config or {})
        self._graph_enabled = bool(self._graph_config.get("enabled", False))
        self._graph: Optional[MemoryGraph] = None
        if self._graph_enabled:
            self._graph = MemoryGraph(
                storage_path=self.storage_path,
                vector_index=None,
                config=self._graph_config,
                encoder=encoder,
            )

        # Phase A: Bayesian posterior (off by default)
        self._bayes_config = dict(bayes_config or {})
        self._bayes_enabled = bool(self._bayes_config.get("enabled", False))

        self._vector_index = VectorIndex(
            namespace="cold_memory",
            storage_dir=self.storage_path,
            model_name=vi_cfg.get("model", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
            embedding_dim=vi_cfg.get("embedding_dim"),
            enabled=vi_cfg.get("enabled", True),
            encoder=encoder,
        )

        self._load()
        self._load_conflicts()
        if len(self._vector_index) == 0 and self._index:
            self.rebuild()
        # First-boot mirror to graph when graph is enabled and the graph is empty
        if self._graph_enabled and self._graph is not None:
            self._mirror_index_to_graph_if_empty()

    def index(self, item: Dict[str, Any], content: str) -> None:
        self.bulk_index([(item, content)])

    def bulk_index(self, items: Sequence[Tuple[Dict[str, Any], str]]) -> int:
        entries: List[Dict[str, Any]] = []
        chunks: List[TextChunk] = []
        timestamp = time.time()
        for offset, (raw_item, content) in enumerate(items):
            item = dict(raw_item)
            write_policy = SharedMemoryPolicy.from_config(
                self._shared_policy_config,
                agent_id=str(item.get("agent_id") or item.get("source_agent") or "default"),
            )
            item = write_policy.apply_index_metadata(item)
            workspace_profile = _normalize_workspace_profile(
                item.get("workspace_profile") or item.get("profile")
            )
            if not write_policy.can_index(workspace_profile):
                raise PermissionError(f"Agent '{write_policy.agent_id}' cannot index {workspace_profile} memory.")
            extra = _shared_memory_extra_metadata(item)
            entry = {
                **extra,
                "id": item.get("id", f"{timestamp}-{offset}"),
                "type": item.get("type", "unknown"),
                "summary": content[:200],
                "timestamp": item.get("timestamp", timestamp),
                "workspace_profile": workspace_profile,
                "agent_id": item.get("agent_id", "default"),
                "visibility": item.get("visibility", "private"),
            }
            entries.append(entry)
            chunks.append(TextChunk(
                id=entry["id"],
                text=entry.get("summary", ""),
                source=entry.get("type", "unknown"),
                meta=dict(entry),
            ))

        if not entries:
            return 0
        self._index.extend(entries)
        self._save()
        self._vector_index.add(chunks)
        # Phase A: mirror new entries to the graph when enabled
        if self._graph is not None:
            for entry in entries:
                node = MemoryNode(
                    id=str(entry.get("id")),
                    type=str(entry.get("type", "unknown")),
                    summary=str(entry.get("summary", "")),
                    workspace_profile=str(entry.get("workspace_profile", "general")),
                    agent_id=str(entry.get("agent_id", "default")),
                    visibility=str(entry.get("visibility", "private")),
                    timestamp=float(entry.get("timestamp", 0.0) or 0.0),
                    claim_key=str(entry.get("claim_key", "") or ""),
                    bayes=dict(entry.get("bayes", {}) or {}),
                )
                try:
                    self._graph.upsert_node(node)
                except Exception:
                    # Graph mirror failures must never block flat indexing
                    continue
        return len(entries)

    def search(
        self,
        query: str,
        top_k: int = 5,
        workspace_profile: str = "general",
        allow_profile_fallback: Optional[bool] = None,
        agent_id: Optional[str] = None,
        shared_policy: Optional[SharedMemoryPolicy] = None,
    ) -> List[Dict[str, Any]]:
        profile = _normalize_workspace_profile(workspace_profile)
        policy = self.profile_policy(profile, top_k=top_k)
        effective_top_k = policy["top_k"]
        memory_policy = shared_policy or self.shared_policy(agent_id)
        filter_fn = _profile_filter(
            profile,
            include_general=policy["include_general"],
            shared_policy=memory_policy,
        )

        results = self._vector_index.search(query, top_k=effective_top_k, filter_fn=filter_fn)
        if results:
            return [chunk.meta for _, chunk in results if chunk.meta]

        if self._fallback_to_keyword:
            keyword_hits = self._keyword_search(
                query,
                effective_top_k,
                workspace_profile=profile,
                include_general=policy["include_general"],
                shared_policy=memory_policy,
            )
            if keyword_hits:
                return keyword_hits

        should_fallback = policy["allow_fallback"] if allow_profile_fallback is None else bool(allow_profile_fallback)
        if should_fallback and profile != "general":
            fallback_results = self._vector_index.search(
                query,
                top_k=effective_top_k,
                filter_fn=_shared_filter(memory_policy),
            )
            if fallback_results:
                return [chunk.meta for _, chunk in fallback_results if chunk.meta]
            if self._fallback_to_keyword:
                return self._keyword_search(
                    query,
                    effective_top_k,
                    shared_policy=memory_policy,
                )
        return []

    def profile_policy(self, workspace_profile: str = "general", top_k: int = 5) -> Dict[str, Any]:
        profile = _normalize_workspace_profile(workspace_profile)
        policy = dict(self._profile_policies.get(profile) or self._profile_policies["general"])
        policy["profile"] = profile
        policy["top_k"] = _positive_int(policy.get("top_k"), top_k)
        policy["include_general"] = bool(policy.get("include_general", profile != "general"))
        policy["allow_fallback"] = bool(policy.get("allow_fallback", profile != "general"))
        return policy

    def shared_policy(self, agent_id: Optional[str] = None) -> SharedMemoryPolicy:
        return SharedMemoryPolicy.from_config(
            self._shared_policy_config,
            agent_id=str(agent_id or "default"),
        )

    def record_shared_outcome(
        self,
        memory_id: str,
        evidence: Dict[str, Any],
        *,
        now: Optional[float] = None,
        misleading_threshold: int = 2,
        stale_after_seconds: float = 90 * 24 * 60 * 60,
    ) -> Dict[str, Any]:
        """Review a cold-memory record for promotion, demotion, or conflict."""
        for index, entry in enumerate(self._index):
            if str(entry.get("id")) != str(memory_id):
                continue
            review = review_shared_memory_outcome(
                entry,
                evidence,
                existing_records=self._index,
                now=now,
                misleading_threshold=misleading_threshold,
                stale_after_seconds=stale_after_seconds,
            )
            self._index[index] = review["entry"]
            for conflict in review.get("conflicts") or []:
                self._append_conflict(conflict)
            self._save()
            self._save_conflicts()
            self.rebuild()
            # Phase A: Bayesian posterior update (ranking signal only).
            # Visibility is still decided by review_shared_memory_outcome().
            bayes_meta: Dict[str, Any] = {}
            if self._bayes_enabled:
                state = _state_from_entry(self._index[index], self._bayes_config)
                evidence_kind = _evidence_to_bayes_kind(evidence)
                if evidence_kind:
                    try:
                        BayesianScorer.update(state, evidence_kind)
                    except ValueError:
                        state = state
                _attach_state_to_entry(self._index[index], state)
                self._save()
                bayes_meta = state.to_dict()
                # Conflict symmetry: when this review produced conflicts, push
                # the conflict update into every involved candidate too.
                for conflict in review.get("conflicts") or []:
                    candidate_id = conflict.get("candidate_id")
                    if not candidate_id or candidate_id == memory_id:
                        continue
                    for j, other in enumerate(self._index):
                        if str(other.get("id")) == str(candidate_id):
                            other_state = _state_from_entry(other, self._bayes_config)
                            BayesianScorer.update(other_state, "conflict")
                            _attach_state_to_entry(self._index[j], other_state)
                            break
                self._save()
            return {
                "memory_id": memory_id,
                "decision": review["decision"],
                "conflicts": review.get("conflicts") or [],
                "entry": dict(self._index[index]),
                "bayes": bayes_meta,
            }
        raise KeyError(f"Cold memory record not found: {memory_id}")

    def shared_conflicts(self, *, unresolved_only: bool = False) -> List[Dict[str, Any]]:
        if not unresolved_only:
            return [dict(item) for item in self._conflicts]
        return [
            dict(item)
            for item in self._conflicts
            if item.get("status") != "resolved"
        ]

    def shared_outcome_summary(self) -> Dict[str, Any]:
        return shared_outcome_summary(self._index, self._conflicts)

    def rebuild(self) -> None:
        """从 JSON 源文件重建向量索引。"""
        self._vector_index.clear()
        chunks = [
            TextChunk(
                id=entry["id"],
                text=entry.get("summary", ""),
                source=entry.get("type", "unknown"),
                meta=dict(entry),
            )
            for entry in self._index
        ]
        self._vector_index.add(chunks)

    def retrieve_with_graph(
        self,
        query: str,
        top_k: int = 5,
        workspace_profile: str = "general",
        expand_hops: Optional[int] = None,
        edge_type_filter: Optional[Iterable[str]] = None,
        include_soft_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        """Phase B graph retrieval: vector first hop + graph expansion +
        five-factor ranking (ADR-0004).

        final_score = 0.55 * vector_score
                    + 0.20 * posterior
                    + 0.10 * freshness_score
                    + 0.10 * edge_support_score
                    + 0.05 * occam_score

        Each returned dict carries the per-factor components and a
        ``fallback`` label (``vector`` | ``keyword`` | ``fake_encoder``)
        so downstream surfaces can distinguish deterministic speed from
        production semantic quality.

        When the graph is disabled, returns an empty list. The flat
        ``search()`` path is unchanged.
        """
        if self._graph is None:
            return []

        # First hop: vector search through the existing flat index, reusing
        # the same profile/agent filter so the graph path never widens the
        # read surface beyond what flat search would have shown.
        shared_policy = self.shared_policy()
        flat = self.search(
            query=query,
            top_k=max(top_k, 10),
            workspace_profile=workspace_profile,
            shared_policy=shared_policy,
        )
        fallback = self._vector_fallback_label()
        # Deduplicate by id and drop first-hop hits that the graph has
        # already soft-deleted. The flat search is unaware of the graph
        # layer, so we re-check here to keep the two surfaces consistent.
        seen: Set[str] = set()
        candidates: List[Dict[str, Any]] = []
        for entry in flat:
            mid = str(entry.get("id"))
            if not mid or mid in seen:
                continue
            if not include_soft_deleted:
                # Ask the graph for the node including soft-deleted; if the
                # returned node is soft-deleted (or absent) we drop it.
                live = self._graph.get_node(mid)
                if live is None and self._graph.get_node(mid, include_soft_deleted=True) is not None:
                    continue
            seen.add(mid)
            candidates.append(entry)

        # Second hop: typed-edge expansion
        for entry in flat:
            mid = str(entry.get("id"))
            if not mid:
                continue
            neighbors = self._graph.neighbors(
                mid,
                edge_types=set(edge_type_filter) if edge_type_filter else None,
                max_hops=expand_hops if expand_hops is not None else self._graph.expand_hops,
            )
            for nid in neighbors:
                if nid in seen:
                    continue
                node = self._graph.get_node(nid)
                if node is None:
                    continue
                if not include_soft_deleted and node.soft_deleted:
                    continue
                # Filter by workspace_profile + shared policy
                if not _profile_matches_entry(
                    node.to_dict(),
                    _normalize_workspace_profile(workspace_profile),
                    include_general=True,
                ):
                    continue
                if not shared_policy.can_read(node.to_dict(), _normalize_workspace_profile(workspace_profile)):
                    continue
                seen.add(nid)
                candidates.append(node.to_dict())

        if not include_soft_deleted:
            candidates = [c for c in candidates if not c.get("soft_deleted")]

        # Score and rank
        now = time.time()
        edge_support = _edge_support_count(self._graph, seen)
        scored: List[Dict[str, Any]] = []
        for cand in candidates:
            mid = str(cand.get("id"))
            v = _vector_score_for(cand, query)
            p = _posterior_for(cand)
            f = _freshness_for(cand, now)
            e = float(edge_support.get(mid, 0))
            o = _occam_for(cand)
            score = 0.55 * v + 0.20 * p + 0.10 * f + 0.10 * e + 0.05 * o
            scored.append({
                **cand,
                "vector_score": round(v, 6),
                "posterior": round(p, 6),
                "freshness_score": round(f, 6),
                "edge_support_score": round(e, 6),
                "occam_score": round(o, 6),
                "graph_score": round(score, 6),
                "fallback": fallback,
            })
        scored.sort(key=lambda x: x["graph_score"], reverse=True)
        return scored[:top_k]

    def _vector_fallback_label(self) -> str:
        """Return ``vector`` / ``keyword`` / ``fake_encoder`` based on the
        actual path the flat search just used. We rely on the public
        ``last_error()`` style probes from VectorIndex.
        """
        # VectorIndex exposes ``is_available``; when False the flat path
        # had to fall back to keyword search.
        vi = self._vector_index
        if vi is None:
            return "keyword"
        if getattr(vi, "is_available", False):
            # When an injected encoder is used, we cannot claim production
            # embedding quality. Mark it fake_encoder for the evidence surface.
            if getattr(vi, "_encoder", None) is not None:
                return "fake_encoder"
            return "vector"
        return "keyword"

    def graph_enabled(self) -> bool:
        return self._graph is not None

    def bayes_enabled(self) -> bool:
        return self._bayes_enabled

    def _mirror_index_to_graph_if_empty(self) -> None:
        """First-boot: if the graph is empty but flat index has entries,
        mirror them. Does not change ids. Idempotent: only runs when the
        graph has no live nodes.
        """
        if self._graph is None:
            return
        if self._graph.get_node("__sentinel__") is not None:
            return
        if any(self._graph.get_node(entry["id"]) for entry in self._index):
            return  # already mirrored
        for entry in self._index:
            node = MemoryNode(
                id=str(entry.get("id")),
                type=str(entry.get("type", "unknown")),
                summary=str(entry.get("summary", "")),
                content_ref="",
                workspace_profile=str(entry.get("workspace_profile", "general")),
                agent_id=str(entry.get("agent_id", "default")),
                visibility=str(entry.get("visibility", "private")),
                timestamp=float(entry.get("timestamp", 0.0) or 0.0),
                claim_key=str(entry.get("claim_key", "") or ""),
                tags=list(entry.get("tags", []) or []),
                bayes=dict(entry.get("bayes", {}) or {}),
            )
            try:
                self._graph.upsert_node(node)
            except Exception:
                # Never let a mirror failure break the runtime
                continue

    def _keyword_search(
        self,
        query: str,
        top_k: int,
        workspace_profile: str = "general",
        include_general: bool = True,
        shared_policy: Optional[SharedMemoryPolicy] = None,
    ) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        profile = _normalize_workspace_profile(workspace_profile)
        memory_policy = shared_policy or self.shared_policy()
        hits = []
        for entry in self._index:
            if not _profile_matches_entry(entry, profile, include_general=include_general):
                continue
            if not memory_policy.can_read(entry, profile):
                continue
            score = 0
            if query_lower in entry.get("summary", "").lower():
                score += 1
            if query_lower in entry.get("type", "").lower():
                score += 1
            if score > 0:
                hits.append((score, entry))
        hits.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in hits[:top_k]]

    def _save(self) -> None:
        self._index_path.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_conflicts(self) -> None:
        self._conflicts_path.write_text(
            json.dumps(self._conflicts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        try:
            self._index = json.loads(self._index_path.read_text(encoding="utf-8"))
            for entry in self._index:
                entry["workspace_profile"] = _normalize_workspace_profile(
                    entry.get("workspace_profile") or entry.get("profile")
                )
                entry["agent_id"] = str(entry.get("agent_id") or entry.get("source_agent") or "default")
                entry["visibility"] = str(entry.get("visibility") or "private")
        except Exception:
            self._index = []

    def _load_conflicts(self) -> None:
        if not self._conflicts_path.exists():
            return
        try:
            raw = json.loads(self._conflicts_path.read_text(encoding="utf-8"))
            self._conflicts = raw if isinstance(raw, list) else []
        except Exception:
            self._conflicts = []

    def _append_conflict(self, conflict: Dict[str, Any]) -> None:
        conflict_id = conflict.get("id")
        if conflict_id and any(item.get("id") == conflict_id for item in self._conflicts):
            return
        self._conflicts.append(dict(conflict))


def _normalize_workspace_profile(value: Any) -> str:
    profile = str(value or "general").strip().lower()
    return profile if profile in _KNOWN_WORKSPACE_PROFILES else "general"


def _shared_memory_extra_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    extra: Dict[str, Any] = {}
    for key in ("claim_key", "shared_memory", "retention", "outcome"):
        if key in item:
            extra[key] = item[key]
    return extra


# ---------------------------------------------------------------------------
# Phase A: Bayesian state helpers
# ---------------------------------------------------------------------------

def _state_from_entry(entry: Dict[str, Any], bayes_config: Dict[str, Any]) -> BayesianState:
    """Build a BayesianState from an entry's stored ``bayes`` sub-object.

    Missing fields fall back to the configured priors. This keeps existing
    entries untouched and lets new evidence accumulate from a known
    starting point.
    """
    alpha_prior = float(bayes_config.get("alpha_prior", 1.0))
    beta_prior = float(bayes_config.get("beta_prior", 1.0))
    raw = entry.get("bayes") if isinstance(entry.get("bayes"), dict) else {}
    alpha = float(raw.get("alpha", alpha_prior))
    beta = float(raw.get("beta", beta_prior))
    occurrences = int(raw.get("occurrences", 0))
    last_update = float(raw.get("last_update", 0.0))
    return BayesianState(
        alpha=max(0.0, alpha),
        beta=max(0.0, beta),
        occurrences=max(0, occurrences),
        last_update=last_update,
    )


def _attach_state_to_entry(entry: Dict[str, Any], state: BayesianState) -> None:
    """Write the BayesianState back into an entry's ``bayes`` sub-object."""
    entry["bayes"] = state.to_dict()


_EVIDENCE_KIND_MAP = {
    "verified": "verified_positive_shared",
    "verified_positive": "verified_positive_shared",
    "pass": "retrieved_success",
    "passed": "retrieved_success",
    "success": "retrieved_success",
    "succeeded": "retrieved_success",
    "fail": "retrieved_failure",
    "failed": "retrieved_failure",
    "failure": "retrieved_failure",
    "regression": "regression",
    "regressed": "regression",
    "contradicted": "regression",
    "misleading": "misleading",
    "misled": "misleading",
    "stale": "stale",
    "expired": "stale",
}


def _evidence_to_bayes_kind(evidence: Dict[str, Any]) -> Optional[str]:
    """Map a ``review_shared_memory_outcome`` evidence dict to a Bayesian kind."""
    if not isinstance(evidence, dict):
        return None
    status = str(evidence.get("status") or evidence.get("outcome") or evidence.get("result") or "").strip().lower()
    if not status:
        return None
    return _EVIDENCE_KIND_MAP.get(status.replace(" ", "_"))


# ---------------------------------------------------------------------------
# Phase B: graph scoring helpers
# ---------------------------------------------------------------------------

def _vector_score_for(cand: Dict[str, Any], query: str) -> float:
    """Token-overlap proxy for vector similarity.

    Real vector similarity comes from the first hop; this is a deterministic
    fallback so the five-factor ranking stays stable when the flat search
    returned keyword results. The result is in [0, 1].
    """
    q_tokens = set(_tokenize(query))
    if not q_tokens:
        return 0.0
    text = str(cand.get("summary", "")) + " " + str(cand.get("type", ""))
    t_tokens = set(_tokenize(text))
    if not t_tokens:
        return 0.0
    return len(q_tokens & t_tokens) / max(1, len(q_tokens))


def _posterior_for(cand: Dict[str, Any]) -> float:
    """Return the Bayesian posterior for a candidate, defaulting to 0.5."""
    bayes = cand.get("bayes")
    if isinstance(bayes, dict):
        post = bayes.get("posterior")
        if isinstance(post, (int, float)):
            return max(0.0, min(1.0, float(post)))
        alpha = bayes.get("alpha")
        beta = bayes.get("beta")
        if isinstance(alpha, (int, float)) and isinstance(beta, (int, float)):
            total = float(alpha) + float(beta)
            if total > 0:
                return max(0.0, min(1.0, float(alpha) / total))
    return 0.5


def _freshness_for(cand: Dict[str, Any], now: float) -> float:
    """Linear freshness in [0, 1] over a 90-day window."""
    ts = cand.get("timestamp")
    if not isinstance(ts, (int, float)) or ts <= 0:
        return 0.0
    age = max(0.0, now - float(ts))
    window = 90.0 * 24.0 * 60.0 * 60.0
    if age >= window:
        return 0.0
    return 1.0 - (age / window)


def _edge_support_count(graph: MemoryGraph, node_ids: Set[str]) -> Dict[str, int]:
    """For each node, count the number of typed edges that already exist
    to any other node in the candidate set. Used as the edge_support_score
    component of the five-factor ranking.
    """
    out: Dict[str, int] = {nid: 0 for nid in node_ids}
    for nid in node_ids:
        for nb in graph.neighbors(nid, max_hops=1):
            if nb in node_ids:
                out[nid] += 1
    return out


def _occam_for(cand: Dict[str, Any]) -> float:
    """Compute Occam score for a candidate. ``summary`` is used when
    present, else content_ref length is used. Tokens approximated as
    ``len(text) // 4``.
    """
    text = str(cand.get("summary", "")) or str(cand.get("content_ref", ""))
    tokens = max(1, len(text) // 4)
    bayes = cand.get("bayes")
    evidence_count = 0
    if isinstance(bayes, dict):
        oc = bayes.get("occurrences")
        if isinstance(oc, (int, float)):
            evidence_count = int(oc)
    return occam_score(summary_tokens=tokens, evidence_count=evidence_count)


def _tokenize(text: str) -> Set[str]:
    """Same tokenizer used by ``memory.graph.MemoryGraph`` so the two
    paths agree on token boundaries.
    """
    out: Set[str] = set()
    s = (text or "").lower()
    if not s:
        return out
    for word in s.split():
        word = word.strip(".,:;!?()[]{}\"'`")
        if len(word) >= 2:
            out.add(word)
    for ch in s:
        if "一" <= ch <= "鿿":
            out.add(ch)
    return out


def _profile_matches_entry(
    entry: Dict[str, Any],
    profile: str,
    include_general: bool = True,
) -> bool:
    if profile == "general":
        return True
    entry_profile = _normalize_workspace_profile(
        entry.get("workspace_profile") or entry.get("profile")
    )
    if entry_profile == profile:
        return True
    return include_general and entry_profile == "general"


def _profile_filter(
    profile: str,
    include_general: bool = True,
    shared_policy: Optional[SharedMemoryPolicy] = None,
):
    if profile == "general":
        return _shared_filter(shared_policy)

    def matches(chunk: TextChunk) -> bool:
        meta = chunk.meta or {}
        if not _profile_matches_entry(
            meta,
            profile,
            include_general=include_general,
        ):
            return False
        if shared_policy is not None and not shared_policy.can_read(meta, profile):
            return False
        return True

    return matches


def _shared_filter(shared_policy: Optional[SharedMemoryPolicy]):
    if shared_policy is None:
        return None

    def matches(chunk: TextChunk) -> bool:
        return shared_policy.can_read(
            chunk.meta or {},
            _normalize_workspace_profile((chunk.meta or {}).get("workspace_profile")),
        )

    return matches


def _resolve_profile_policies(raw: Any) -> Dict[str, Dict[str, Any]]:
    policies = {profile: dict(policy) for profile, policy in _DEFAULT_PROFILE_POLICIES.items()}
    if not isinstance(raw, dict):
        return policies
    for key, value in raw.items():
        profile = _normalize_workspace_profile(key)
        if not isinstance(value, dict):
            continue
        next_policy = dict(policies.get(profile, policies["general"]))
        for field in ("top_k", "include_general", "allow_fallback"):
            if field in value:
                next_policy[field] = value[field]
        policies[profile] = next_policy
    return policies


def _positive_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = int(default)
    return max(1, number)
