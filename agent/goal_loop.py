"""Goal-level engineering loop for TTMEvolve.

GoalLoop is the default task orchestrator. It turns a user task into a
GoalRun and advances it through fixed engineering stages. Each stage receives
only a StageHandoff from the previous stage, emits reviewable evidence, and
hands a compact input to the next stage.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
import json
import os
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional


GOAL_LOOP_VERSION = "goal-loop.v1"

GOAL_STAGES: List[str] = [
    "UNDERSTAND",
    "DOC_READ",
    "RESEARCH",
    "PROPOSE",
    "CONFIRM",
    "DEV",
    "BUILD",
    "REV",
    "REPORT",
    "POST",
]

READ_ONLY_STAGES = {"UNDERSTAND", "DOC_READ", "RESEARCH", "PROPOSE", "REV", "REPORT"}
CONTRACT_WRITE_STAGES = {"CONFIRM"}
SIDE_EFFECT_STAGES = {"DEV", "BUILD", "POST"}
RECURSIVE_STAGES = {"PROPOSE", "DEV", "REV"}
# Stages whose failure means the implementation itself must be redone, so they
# kick the loop back to DEV instead of retrying themselves in place.
REWORK_TRIGGER_STAGES = {"BUILD", "REV"}
DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_STAGE_RETRIES = 1
DEFAULT_MAX_REWORK_CYCLES = 1
DEFAULT_MAX_SUBGOALS = 3


EmitFn = Callable[[Dict[str, Any]], None]
ConfirmFn = Callable[[str], bool]
DevRunner = Callable[[str, str], Dict[str, Any]]
CancelCheck = Callable[[], bool]
SubGoalRunner = Callable[[List[str], str, int], List[Dict[str, Any]]]
# Optional callback that returns the project_control / project_state dicts
# the POST writeback planner needs. GoalLoop falls back to a derived
# minimal control summary when no builder is supplied.
ProjectControlBuilder = Callable[["GoalRun"], Dict[str, Any]]


@dataclass
class StageReview:
    verdict: str
    issues: List[str] = field(default_factory=list)
    next_input: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StageHandoff:
    from_stage: str
    to_stage: str
    goal_id: str
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StageRun:
    stage: str
    input: Dict[str, Any]
    output: Dict[str, Any] = field(default_factory=dict)
    review: Dict[str, Any] = field(default_factory=dict)
    handoff: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    retry_count: int = 0
    artifacts: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class GoalRun:
    goal_id: str
    session_id: str
    task: str
    status: str = "running"
    current_stage: str = "UNDERSTAND"
    depth: int = 0
    budget: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    stages: List[StageRun] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    sub_goals: List[Dict[str, Any]] = field(default_factory=list)


class GoalLoopError(RuntimeError):
    """Raised when GoalLoop cannot proceed safely."""


class GoalDocRouter:
    """Deterministic document preload for GoalLoop DOC_READ."""

    ARCHITECTURE_KEYWORDS = (
        "architecture",
        "架构",
        "重构",
        "控制论",
        "loop",
        "agent",
        "runtime",
        "plan",
        "memory",
        "rag",
    )
    MAKER_KEYWORDS = ("maker", "taptap", "tapmaker", "mcp", "游戏")

    def __init__(self, project_root: Path, *, max_excerpt_chars: int = 1800):
        self.project_root = Path(project_root)
        self.max_excerpt_chars = int(max_excerpt_chars)

    def route(self, task: str) -> List[Dict[str, Any]]:
        text = str(task or "").lower()
        docs = [
            "AGENTS.md",
            "docs/memory-index.md",
        ]
        if self._has_any(text, self.ARCHITECTURE_KEYWORDS):
            docs.extend(
                [
                    "docs/architecture/architecture-control-roadmap-2026-06-27.md",
                    "docs/architecture/adr-0003-modular-monolith-runtime-event-bus.md",
                    "docs/architecture/adr-0008-plan-v2-cybernetic-control.md",
                    "docs/react-loop-redesign.md",
                    "docs/feature-flags.md",
                ]
            )
        if self._has_any(text, self.MAKER_KEYWORDS):
            docs.extend(
                [
                    "docs/persona.md",
                    "docs/getting-started.md",
                ]
            )
        return [self._read_doc(path) for path in self._dedupe(docs)]

    def _read_doc(self, rel_path: str) -> Dict[str, Any]:
        path = (self.project_root / rel_path).resolve()
        root = self.project_root.resolve()
        if root not in [path, *path.parents]:
            return {"path": rel_path, "exists": False, "error": "outside_project_root"}
        if not path.exists() or not path.is_file():
            return {"path": rel_path, "exists": False}
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as exc:
            return {"path": rel_path, "exists": True, "error": str(exc)}
        excerpt = text[: self.max_excerpt_chars]
        return {
            "path": rel_path,
            "exists": True,
            "chars": len(text),
            "excerpt": excerpt,
            "truncated": len(text) > len(excerpt),
        }

    @staticmethod
    def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword.lower() in text for keyword in keywords)

    @staticmethod
    def _dedupe(items: List[str]) -> List[str]:
        seen = set()
        out = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out


class GoalLoop:
    """Run one user goal through TTMEvolve's engineering stages."""

    def __init__(
        self,
        *,
        project_root: Path,
        emit: Optional[EmitFn] = None,
        confirm: Optional[ConfirmFn] = None,
        dev_runner: Optional[DevRunner] = None,
        cancel_check: Optional[CancelCheck] = None,
        approval_policy: str = "on-request",
        max_depth: int = DEFAULT_MAX_DEPTH,
        build_command: str = "",
        llm: Optional[Any] = None,
        max_stage_retries: int = DEFAULT_MAX_STAGE_RETRIES,
        max_rework_cycles: int = DEFAULT_MAX_REWORK_CYCLES,
        sub_goal_runner: Optional[SubGoalRunner] = None,
        max_subgoals: int = DEFAULT_MAX_SUBGOALS,
        max_concurrent_subgoals: int = 3,
        auto_post: bool = False,
        post_apply: bool = False,
        project_control_builder: Optional[ProjectControlBuilder] = None,
        artifacts_root: Optional[Path] = None,
    ):
        # ``artifacts_root`` is the parent directory for every
        # file GoalLoop writes (decisions, contracts, progress,
        # sprint board, skill packs). It defaults to
        # ``project_root`` so production behaviour is unchanged;
        # tests pass a tmp dir to keep the real project clean.
        # ``TTMEVOLVE_GOAL_ARTIFACTS_ROOT`` overrides the default
        # for ad-hoc runs (manual demos, sub-process tests).
        self.project_root = Path(project_root)
        env_override = os.environ.get("TTMEVOLVE_GOAL_ARTIFACTS_ROOT")
        if artifacts_root is None and env_override:
            artifacts_root = Path(env_override)
        self.artifacts_root = (
            Path(artifacts_root).resolve() if artifacts_root is not None else self.project_root.resolve()
        )
        self.emit = emit
        self.confirm = confirm
        self.dev_runner = dev_runner
        self.cancel_check = cancel_check
        self.approval_policy = str(approval_policy or "on-request")
        self.max_depth = int(max_depth)
        self.build_command = str(build_command or "")
        self.llm = llm
        self.max_stage_retries = max(0, int(max_stage_retries))
        self.max_rework_cycles = max(0, int(max_rework_cycles))
        self.sub_goal_runner = sub_goal_runner or self._default_sub_goal_runner
        self.max_subgoals = max(0, int(max_subgoals))
        self.max_concurrent_subgoals = max(1, int(max_concurrent_subgoals))
        self.auto_post = bool(auto_post)
        self.post_apply = bool(post_apply)
        self.project_control_builder = project_control_builder
        self.doc_router = GoalDocRouter(self.project_root)

    @property
    def paths(self) -> Dict[str, Path]:
        """Resolved artifact paths. Everything GoalLoop writes
        lands under ``self.artifacts_root`` so production runs hit
        the project tree while tests can redirect to a tmp dir.

        Keys:
            - ``decisions``: directory for per-goal decision notes.
            - ``system_contracts_goals``: directory for the
              CONFIRM-stage contract markdown.
            - ``progress_md``: PM-style progress dashboard.
            - ``sprint_board_md``: PM-style sprint board.
            - ``skill_packs``: project-side knowledge base.
        """
        root = self.artifacts_root
        return {
            "decisions": root / "decisions",
            "system_contracts_goals": root / "system-contracts" / "goals",
            "progress_md": root / "docs" / "progress.md",
            "sprint_board_md": root / "docs" / "sprint-board.md",
            "skill_packs": root / "docs" / "skill_packs",
        }

    def run(self, task: str, *, session_id: str, depth: int = 0) -> Dict[str, Any]:
        if depth > self.max_depth:
            raise GoalLoopError(f"goal recursion depth {depth} exceeds max_depth {self.max_depth}")
        goal = GoalRun(
            goal_id=self._goal_id(session_id),
            session_id=session_id,
            task=task,
            depth=depth,
            budget={
                "max_depth": self.max_depth,
                "stages": len(GOAL_STAGES),
                "max_subgoals": self.max_subgoals,
            },
        )
        self._emit(session_id, "goal_started", self._goal_payload(goal))

        handoff = StageHandoff(
            from_stage="USER",
            to_stage="UNDERSTAND",
            goal_id=goal.goal_id,
            summary="User goal received.",
            data={"task": task},
        )
        final_output = ""
        blocked_reason = ""
        stage_attempts: Dict[str, int] = {}

        index = 0
        while index < len(GOAL_STAGES):
            stage = GOAL_STAGES[index]
            self._check_cancelled()
            goal.current_stage = stage
            stage_attempts[stage] = stage_attempts.get(stage, 0) + 1
            stage_run = StageRun(
                stage=stage,
                input=asdict(handoff),
                status="running",
                retry_count=stage_attempts[stage] - 1,
            )
            goal.stages.append(stage_run)
            self._emit(session_id, "goal_stage_started", self._stage_payload(goal, stage_run))
            output = self._run_stage(stage, goal, handoff)
            stage_run.output = output
            stage_run.artifacts = output.get("artifacts", []) if isinstance(output.get("artifacts"), list) else []
            self._emit(session_id, "goal_stage_output", self._stage_payload(goal, stage_run))

            review = self._review_stage(stage, output)
            stage_run.review = asdict(review)
            self._emit(session_id, "goal_stage_review", self._stage_payload(goal, stage_run))

            if review.verdict == "blocked":
                stage_run.status = "blocked"
                goal.status = "blocked"
                blocked_reason = "; ".join(review.issues) or f"{stage} blocked"
                self._emit(session_id, "goal_blocked", {**self._goal_payload(goal), "reason": blocked_reason})
                break

            if review.verdict == "needs_fix":
                target = self._plan_fix(stage, goal, stage_attempts)
                if target is not None:
                    stage_run.status = "needs_fix"
                    target_index, handoff = self._apply_fix(
                        goal, stage, index, target, review, stage_attempts, handoff
                    )
                    index = target_index
                    continue

            stage_run.status = "done" if review.verdict == "pass" else "needs_fix"
            for artifact in stage_run.artifacts:
                goal.artifacts.append(artifact)
                self._emit(
                    session_id,
                    "goal_artifact_written",
                    {"goal_id": goal.goal_id, "stage": stage, "artifact": artifact},
                )
            next_stage = self._next_stage(stage)
            if next_stage:
                handoff = self._compile_handoff(goal, stage, next_stage, output, review)
                stage_run.handoff = asdict(handoff)
                self._emit(session_id, "goal_stage_handoff", self._stage_payload(goal, stage_run))
            if stage == "REPORT":
                final_output = str(output.get("report") or output.get("summary") or "")
            index += 1

        if goal.status != "blocked":
            goal.status = "completed"
            self._emit(session_id, "goal_completed", self._goal_payload(goal))
        if not final_output:
            final_output = blocked_reason or self._final_report(goal)

        trajectory = [self._trajectory_step(index, run) for index, run in enumerate(goal.stages)]
        side_channel: Dict[str, Any] = {}
        for run in goal.stages:
            if run.stage != "DEV":
                continue
            output = run.output if isinstance(run.output, dict) else {}
            dev_result = output.get("dev_result") if isinstance(output.get("dev_result"), dict) else {}
            for key, value in dev_result.items():
                if not key.startswith("_"):
                    continue
                # Strip the leading underscore so the top-level key is
                # ergonomic (``dev_memory_index`` not ``_memory_index``) and
                # avoid clobbering reserved result fields.
                public = f"dev_{key.lstrip('_')}"
                if public not in side_channel and public not in {
                    "session_id", "task", "output", "done",
                    "goal_loop", "trajectory", "iteration_count",
                }:
                    side_channel[public] = value
        return {
            "session_id": session_id,
            "task": task,
            "output": final_output,
            "done": goal.status == "completed",
            "goal_loop": self._goal_payload(goal),
            "trajectory": trajectory,
            "iteration_count": len(trajectory),
            **side_channel,
        }

    def _plan_fix(
        self, stage: str, goal: GoalRun, stage_attempts: Dict[str, int]
    ) -> Optional[Dict[str, Any]]:
        """Decide how to recover from a needs_fix verdict within budget.

        Returns a fix plan ``{"mode", "target_stage"}`` or ``None`` when no
        budget remains and the loop should accept the degraded result and move
        on. REV/BUILD failures route back to DEV (rework); other stages retry
        themselves in place.
        """
        if stage in REWORK_TRIGGER_STAGES and "DEV" in GOAL_STAGES:
            # The first DEV run is the normal pass; every extra one is a rework.
            dev_runs = sum(1 for run in goal.stages if run.stage == "DEV")
            rework_used = max(0, dev_runs - 1)
            if rework_used < self.max_rework_cycles:
                return {"mode": "rework", "target_stage": "DEV"}
            return None
        if (stage_attempts.get(stage, 1) - 1) < self.max_stage_retries:
            return {"mode": "retry", "target_stage": stage}
        return None

    def _apply_fix(
        self,
        goal: GoalRun,
        stage: str,
        index: int,
        plan: Dict[str, Any],
        review: StageReview,
        stage_attempts: Dict[str, int],
        current_handoff: StageHandoff,
    ) -> tuple[int, StageHandoff]:
        """Build the corrective handoff and return the next loop index."""
        target_stage = str(plan.get("target_stage") or stage)
        mode = str(plan.get("mode") or "retry")
        target_index = GOAL_STAGES.index(target_stage)
        # When reworking we re-run from the target stage; counters for stages
        # between target and the failing stage reset so their attempt budget
        # applies to the fresh cycle.
        if mode == "rework":
            for between in GOAL_STAGES[target_index : index + 1]:
                stage_attempts.pop(between, None)
        issues = review.issues or [f"{stage} needs fix"]
        # Retrying in place must preserve the stage's upstream input (e.g.
        # PROPOSE keeps RESEARCH constraints); rework starts a fresh DEV input.
        data: Dict[str, Any] = dict(current_handoff.data) if mode == "retry" else {}
        data.update(
            {
                "fix_mode": mode,
                "failed_stage": stage,
                "issues": issues,
                "summary": f"Address review issues from {stage}.",
            }
        )
        handoff = StageHandoff(
            from_stage=stage,
            to_stage=target_stage,
            goal_id=goal.goal_id,
            summary=f"{mode.upper()} after {stage}: {issues[0]}",
            data=data,
        )
        self._emit(
            goal.session_id,
            "goal_stage_fix",
            {
                "goal_id": goal.goal_id,
                "from_stage": stage,
                "target_stage": target_stage,
                "mode": mode,
                "issues": issues,
            },
        )
        return target_index, handoff

    def _default_sub_goal_runner(
        self, tasks: List[str], session_id: str, parent_depth: int
    ) -> List[Dict[str, Any]]:
        """Default sub-goal runner: recurse into this same GoalLoop one level deeper.

        Each child is a synchronous full GoalRun with its own goal_id, emits
        its own goal_* events at the session level, and surfaces a compact
        summary back to the parent. Failures are captured per child — they
        never raise into the parent.
        """
        results: List[Dict[str, Any]] = []
        for index, sub_task in enumerate(tasks, start=1):
            sub_session = f"{session_id}#sub{parent_depth}.{index}"
            sub_id = self._goal_id(sub_session)
            try:
                sub_result = self.run(sub_task, session_id=sub_session, depth=parent_depth + 1)
                results.append(
                    {
                        "goal_id": sub_id,
                        "task": sub_task,
                        "status": "completed" if sub_result.get("done") else "failed",
                        "summary": str(sub_result.get("output") or "")[:400],
                        "iteration_count": sub_result.get("iteration_count", 0),
                    }
                )
            except GoalLoopError as exc:
                # Depth limit / config rejection becomes a soft failure, not a crash.
                results.append(
                    {
                        "goal_id": sub_id,
                        "task": sub_task,
                        "status": "rejected",
                        "summary": str(exc),
                    }
                )
            except Exception as exc:  # any other failure must not kill the parent
                results.append(
                    {
                        "goal_id": sub_id,
                        "task": sub_task,
                        "status": "failed",
                        "summary": f"sub-goal crashed: {exc}"[:400],
                    }
                )
        return results

    def _run_stage(self, stage: str, goal: GoalRun, handoff: StageHandoff) -> Dict[str, Any]:
        if stage == "UNDERSTAND":
            return self._stage_understand(goal, handoff)
        if stage == "DOC_READ":
            return self._stage_doc_read(goal, handoff)
        if stage == "RESEARCH":
            return self._stage_research(goal, handoff)
        if stage == "PROPOSE":
            return self._stage_propose(goal, handoff)
        if stage == "CONFIRM":
            return self._stage_confirm(goal, handoff)
        if stage == "DEV":
            return self._stage_dev(goal, handoff)
        if stage == "BUILD":
            return self._stage_build(goal, handoff)
        if stage == "REV":
            return self._stage_rev(goal, handoff)
        if stage == "REPORT":
            return self._stage_report(goal, handoff)
        if stage == "POST":
            return self._stage_post(goal, handoff)
        raise GoalLoopError(f"unknown goal stage: {stage}")

    def _reason(
        self,
        goal: GoalRun,
        *,
        stage: str,
        instruction: str,
        context: str = "",
        expect: str = "object",
    ) -> Optional[Any]:
        """Run one stage-level LLM reasoning step.

        Returns the parsed JSON value (object or list) on success. Returns
        ``None`` when no LLM is configured, the call fails, or the output is
        not parseable — the caller then falls back to deterministic template
        logic so GoalLoop never depends on an available model to make progress.
        """
        reflect = getattr(self.llm, "reflect", None)
        if not callable(reflect):
            return None
        shape = "a JSON array" if expect == "array" else "a single JSON object"
        prompt = (
            f"You are the {stage} stage of an engineering goal loop.\n"
            f"Goal: {goal.task}\n"
            f"{context}\n\n"
            f"{instruction}\n\n"
            f"Respond with ONLY {shape}. No prose, no markdown fences."
        )
        try:
            raw = reflect(prompt)
        except Exception as exc:  # model/transport failure must not abort the goal
            self._emit(
                goal.session_id,
                "goal_reasoning_failed",
                {"goal_id": goal.goal_id, "stage": stage, "error": str(exc)[:200]},
            )
            return None
        parsed = self._parse_json(raw)
        if parsed is None:
            self._emit(
                goal.session_id,
                "goal_reasoning_failed",
                {"goal_id": goal.goal_id, "stage": stage, "error": "unparseable_llm_output"},
            )
            return None
        if expect == "array" and not isinstance(parsed, list):
            return None
        if expect == "object" and not isinstance(parsed, dict):
            return None
        return parsed

    @staticmethod
    def _parse_json(raw: Any) -> Optional[Any]:
        """Best-effort JSON extraction from a raw LLM string."""
        if isinstance(raw, (dict, list)):
            return raw
        text = str(raw or "").strip()
        if not text:
            return None
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z0-9]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text).strip()
        try:
            return json.loads(text)
        except Exception:
            pass
        for opener, closer in (("{", "}"), ("[", "]")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    continue
        return None

    def _stage_understand(self, goal: GoalRun, handoff: StageHandoff) -> Dict[str, Any]:
        task = str(handoff.data.get("task") or goal.task)
        # Auto-recall project-side skill packs so the LLM has working
        # knowledge available before it reasons. Falls back silently
        # when no packs are configured.
        recalled_packs = self._recall_skill_packs(task)
        if recalled_packs:
            self._emit(
                goal.session_id,
                "goal_skill_packs_recalled",
                {
                    "goal_id": goal.goal_id,
                    "packs": [r.to_dict() for r in recalled_packs],
                },
            )
        context_block = ""
        if recalled_packs:
            context_lines = ["Project-side knowledge (skill packs):"]
            for r in recalled_packs:
                context_lines.append(
                    f"- [{r.pack.scope}] {r.pack.name}: {r.pack.summary}"
                )
            context_block = "\n".join(context_lines)
        reasoned = self._reason(
            goal,
            stage="UNDERSTAND",
            context=context_block,
            instruction=(
                "Restate the goal in one sentence and break it into concrete, "
                "verifiable subtasks plus measurable success criteria. Keys: "
                '"restated_goal" (string), "subtasks" (array of strings), '
                '"success_criteria" (array of strings), "open_questions" (array of strings).'
            ),
        )
        summary = task
        success_criteria: List[str] = []
        open_questions: List[str] = []
        if reasoned:
            subtasks = self._string_list(reasoned.get("subtasks")) or self._subtasks(task)
            summary = str(reasoned.get("restated_goal") or task)
            success_criteria = self._string_list(reasoned.get("success_criteria"))
            open_questions = self._string_list(reasoned.get("open_questions"))
            reasoning = "llm"
        else:
            subtasks = self._subtasks(task)
            reasoning = "template"
        message_lines = [
            "GoalLoop UNDERSTAND",
            f"Goal: {summary}",
            "Subtasks:",
            *[f"- {item}" for item in subtasks],
        ]
        if success_criteria:
            message_lines.extend(["Success criteria:", *[f"- {item}" for item in success_criteria]])
        approved = self._request_confirmation(
            goal,
            stage="UNDERSTAND",
            title="Confirm goal understanding",
            message="\n".join(message_lines),
            strength="light",
        )
        return {
            "ok": approved,
            "summary": summary,
            "subtasks": subtasks,
            "success_criteria": success_criteria,
            "open_questions": open_questions,
            "reasoning": reasoning,
            "requires_confirmation": True,
            "confirmed": approved,
            "permissions": self._permissions_for("UNDERSTAND"),
        }

    def _stage_doc_read(self, goal: GoalRun, handoff: StageHandoff) -> Dict[str, Any]:
        docs = self.doc_router.route(goal.task)
        return {
            "ok": True,
            "summary": f"Loaded {sum(1 for item in docs if item.get('exists'))}/{len(docs)} required docs.",
            "docs": docs,
            "permissions": self._permissions_for("DOC_READ"),
        }

    def _stage_research(self, goal: GoalRun, handoff: StageHandoff) -> Dict[str, Any]:
        docs = handoff.data.get("docs") if isinstance(handoff.data.get("docs"), list) else []
        existing = [doc for doc in docs if isinstance(doc, dict) and doc.get("exists")]
        doc_paths = [str(doc.get("path")) for doc in existing]
        reasoned = self._reason(
            goal,
            stage="RESEARCH",
            context=self._docs_context(existing),
            instruction=(
                "From the loaded project documents above, extract the constraints and "
                "prior decisions that must shape the implementation, plus the risks they "
                "imply. Keys: \"constraints\" (array of strings), \"risks\" (array of strings), "
                "\"summary\" (string)."
            ),
        )
        if reasoned:
            constraints = self._string_list(reasoned.get("constraints"))[:12] or doc_paths[:12]
            risks = self._string_list(reasoned.get("risks"))[:8]
            summary = str(reasoned.get("summary") or "Researched constraints from project documents.")
            reasoning = "llm"
        else:
            constraints = doc_paths[:12]
            risks = []
            summary = "Collected existing documentation and constraints for the goal."
            reasoning = "template"
        return {
            "ok": True,
            "summary": summary,
            "constraints": constraints,
            "risks": risks,
            "source_docs": doc_paths[:12],
            "reasoning": reasoning,
            "memory_boundary": "project memory is product memory, not assistant private memory",
            "permissions": self._permissions_for("RESEARCH"),
        }

    def _stage_propose(self, goal: GoalRun, handoff: StageHandoff) -> Dict[str, Any]:
        constraints = self._string_list(handoff.data.get("constraints"))
        prior_risks = self._string_list(handoff.data.get("risks"))
        context_lines = []
        if constraints:
            context_lines.append("Constraints from research:\n" + "\n".join(f"- {c}" for c in constraints[:12]))
        if prior_risks:
            context_lines.append("Risks raised in research:\n" + "\n".join(f"- {r}" for r in prior_risks[:8]))
        reasoned = self._reason(
            goal,
            stage="PROPOSE",
            context="\n\n".join(context_lines),
            instruction=(
                "Propose how to implement this goal within the constraints above. Keys: "
                '"recommended" (string, the single recommended approach), '
                '"alternatives" (array of strings), "risks" (array of strings), '
                '"acceptance" (array of strings, verifiable acceptance criteria), '
                '"sub_goals" (optional array of objects, each with '
                '"task (string), type (one of: code, asset, scene, audio, integration, test), '
                "depends_on (array of sub_goal ids this one waits for), "
                '"acceptance (array of strings), model_hint (one of: fast, balanced, deep), '
                '"assigned_agent (string, optional)). When the work is too large for one goal, '
                'list 2-6 well-bounded sub_goals; otherwise leave the array empty. '
                'Always include a final integration sub_goal that depends_on every other sub_goal.'
            ),
        )
        if reasoned and reasoned.get("recommended"):
            proposal = {
                "recommended": str(reasoned.get("recommended")),
                "alternatives": self._string_list(reasoned.get("alternatives")),
                "risks": self._string_list(reasoned.get("risks")) or prior_risks,
                "acceptance": self._string_list(reasoned.get("acceptance")),
            }
            proposed_subgoals_raw = reasoned.get("sub_goals")
            reasoning = "llm"
        else:
            proposal = {
                "recommended": "Run GoalLoop as the default task orchestrator and use ReAct as the DEV-stage executor.",
                "alternatives": [
                    "Use agent.loop_engine=react for emergency fallback.",
                    "Keep future sub-goals bounded to PROPOSE/DEV/REV with max_depth=2.",
                ],
                "risks": prior_risks or [
                    "Human confirmation can block unattended runs; approval.policy=never auto-confirms.",
                    "BUILD is only real when goal_loop.build_command is configured.",
                ],
                "acceptance": [
                    "GoalLoop events are persisted and visible in Evidence Bundle.",
                    "CONFIRM writes contract and decision artifacts before DEV.",
                    "REPORT truthfully lists build/review status.",
                ],
            }
            proposed_subgoals_raw = []
            reasoning = "template"
        sub_goal_results: List[Dict[str, Any]] = []
        if (
            proposed_subgoals_raw
            and goal.depth < self.max_depth
            and self.max_subgoals > 0
        ):
            # Branch on runner: if the user supplied a custom
            # sub_goal_runner (legacy interface: takes a list of
            # strings), keep the old string-list path for backward
            # compatibility. Otherwise use the typed DAG.
            user_runner = self._user_supplied_subgoal_runner()
            if user_runner is not None:
                tasks = [
                    str(item.get("task") if isinstance(item, dict) else item)
                    for item in proposed_subgoals_raw
                    if isinstance(item, (str, dict))
                ][: self.max_subgoals]
                sub_goal_results = self._run_legacy_subgoal_runner(
                    user_runner, tasks, goal,
                )
            else:
                specs = self._coerce_subgoal_specs(proposed_subgoals_raw, goal)
                if specs:
                    sub_goal_results = self._run_subgoal_dag(specs, goal)
            for sub in sub_goal_results:
                if not isinstance(sub, dict):
                    continue
                sub.setdefault("parent_goal_id", goal.goal_id)
                goal.sub_goals.append(sub)
        return {
            "ok": True,
            "summary": proposal["recommended"],
            "proposal": proposal,
            "sub_goal_results": sub_goal_results,
            "reasoning": reasoning,
            "recursive_allowed": goal.depth < self.max_depth,
            "permissions": self._permissions_for("PROPOSE"),
        }

    def _stage_confirm(self, goal: GoalRun, handoff: StageHandoff) -> Dict[str, Any]:
        proposal = handoff.data.get("proposal") if isinstance(handoff.data.get("proposal"), dict) else {}
        message = (
            "GoalLoop CONFIRM\n"
            f"Goal: {goal.task}\n"
            f"Recommended: {proposal.get('recommended') or handoff.summary}\n"
            "Approve writing system contract and decision artifacts before DEV?"
        )
        approved = self._request_confirmation(
            goal,
            stage="CONFIRM",
            title="Confirm implementation proposal",
            message=message,
            strength="strong",
        )
        artifacts: List[Dict[str, Any]] = []
        if approved:
            artifacts = self._write_confirm_artifacts(goal, proposal)
        return {
            "ok": approved,
            "summary": "Proposal confirmed." if approved else "Proposal rejected.",
            "confirmed": approved,
            "artifacts": artifacts,
            "permissions": self._permissions_for("CONFIRM"),
        }

    def _stage_dev(self, goal: GoalRun, handoff: StageHandoff) -> Dict[str, Any]:
        is_rework = handoff.data.get("fix_mode") == "rework"
        issues = self._string_list(handoff.data.get("issues"))
        if not self.dev_runner:
            return {
                "ok": True,
                "summary": "No DEV runner configured; stage recorded as skipped.",
                "skipped": True,
                "rework": is_rework,
                "permissions": self._permissions_for("DEV"),
            }
        dev_task = goal.task
        if issues:
            dev_task = (
                f"{goal.task}\n\n"
                "This DEV run is a fix attempt after review found issues. Address these:\n"
                + "\n".join(f"- {item}" for item in issues)
            )
        result = self.dev_runner(dev_task, goal.session_id) or {}
        return {
            "ok": result.get("done", True) is not False and not result.get("error"),
            "summary": result.get("output") or "DEV runner completed.",
            "dev_result": self._compact_dev_result(result),
            "rework": is_rework,
            "permissions": self._permissions_for("DEV"),
        }

    def _stage_build(self, goal: GoalRun, handoff: StageHandoff) -> Dict[str, Any]:
        if not self.build_command:
            return {
                "ok": True,
                "summary": "No goal_loop.build_command configured; build marked not_configured.",
                "status": "not_configured",
                "permissions": self._permissions_for("BUILD"),
            }
        import subprocess

        started = time.time()
        proc = subprocess.run(
            self.build_command,
            cwd=str(self.project_root),
            shell=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        return {
            "ok": proc.returncode == 0,
            "summary": "Build passed." if proc.returncode == 0 else "Build failed.",
            "status": "passed" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "elapsed_ms": round((time.time() - started) * 1000, 2),
            "stdout_tail": (proc.stdout or "")[-1200:],
            "stderr_tail": (proc.stderr or "")[-1200:],
            "permissions": self._permissions_for("BUILD"),
        }

    def _stage_rev(self, goal: GoalRun, handoff: StageHandoff) -> Dict[str, Any]:
        # Deterministic floor: hard facts must surface regardless of the model.
        issues = []
        if handoff.data.get("status") == "failed" or handoff.data.get("ok") is False:
            issues.append("Build or DEV stage reported failure.")
        if not goal.artifacts:
            issues.append("No CONFIRM artifacts were recorded.")
        intent_match = not issues
        reasoning = "template"
        reasoned = self._reason(
            goal,
            stage="REV",
            context=self._rev_context(goal, handoff),
            instruction=(
                "Review whether the executed work matches the original goal intent. "
                'Keys: "intent_match" (boolean), "issues" (array of strings), '
                '"summary" (string).'
            ),
        )
        if reasoned is not None:
            reasoning = "llm"
            for issue in self._string_list(reasoned.get("issues")):
                if issue not in issues:
                    issues.append(issue)
            # The model can only lower confidence, never override a hard failure.
            intent_match = bool(reasoned.get("intent_match")) and not (
                handoff.data.get("status") == "failed" or handoff.data.get("ok") is False
            )
        return {
            "ok": not issues,
            "summary": (
                "Review passed." if not issues else "Review found issues."
            ),
            "issues": issues,
            "intent_match": intent_match,
            "reasoning": reasoning,
            "permissions": self._permissions_for("REV"),
        }

    def _stage_report(self, goal: GoalRun, handoff: StageHandoff) -> Dict[str, Any]:
        report = self._final_report(goal)
        # Forward any due-file hints the proposal layer or caller attached so
        # POST can write to a project-specific allowlist instead of the default.
        due = handoff.data.get("memory_updates_due")
        return {
            "ok": True,
            "summary": "GoalLoop report ready.",
            "report": report,
            "memory_updates_due": due if isinstance(due, list) else None,
            "permissions": self._permissions_for("REPORT"),
        }

    def _stage_post(self, goal: GoalRun, handoff: StageHandoff) -> Dict[str, Any]:
        # PM slice: advance the feature ledger and refresh the
        # sprint board. This is independent of the writeback path;
        # a feature state change always records itself.
        feature_summary = self._update_feature_state(goal)
        # POST closes the goal with a project-writeback step. Two layers of
        # safety remain even when auto_post is on: a guarded plan builder
        # whitelists target files and uses idempotency markers, and apply is
        # only ever called when the plan is explicitly `applicable`.
        due_items = handoff.data.get("memory_updates_due")
        if not isinstance(due_items, list) or not due_items:
            # Fall back to the two always-relevant POST docs so the goal
            # always produces evidence; producers (REPORT) can override.
            due_items = [{"gate": "POST", "file": "docs/memory-index.md"}, {"gate": "POST", "file": "docs/sprint-board.md"}]
        due_items = [item for item in due_items if isinstance(item, dict) and item.get("file")]
        if not due_items:
            return {
                "ok": True,
                "summary": "POST skipped: no memory updates due.",
                "memory_updates_due": [],
                "skipped": True,
                "permissions": self._permissions_for("POST"),
            }
        project_control, project_state = self._project_control_for(goal, due_items)
        try:
            from server.project_writeback import (
                apply_project_writeback_plan,
                build_project_writeback_plan,
                compact_project_writeback,
            )
        except Exception as exc:
            # The writeback module is an optional capability; missing deps
            # must never block a goal from completing.
            return {
                "ok": True,
                "summary": f"POST skipped: writeback module unavailable ({exc})",
                "memory_updates_due": due_items,
                "skipped": True,
                "permissions": self._permissions_for("POST"),
            }
        plan = build_project_writeback_plan(
            project_root=self.project_root,
            session_id=goal.session_id,
            project_state=project_state,
            project_control=project_control,
        )
        result: Dict[str, Any] = {
            "ok": True,
            "summary": "POST plan built.",
            "memory_updates_due": due_items,
            "plan": compact_project_writeback(plan),
            "auto_post": self.auto_post,
            "post_apply": self.post_apply,
            "feature": feature_summary,
            "permissions": self._permissions_for("POST"),
        }
        if self.auto_post and plan.get("applicable"):
            applied = apply_project_writeback_plan(self.project_root, plan)
            result["applied"] = applied
            result["summary"] = (
                f"POST applied: {applied.get('applied_count', 0)} file(s) updated, "
                f"{applied.get('skipped_count', 0)} skipped, "
                f"{applied.get('error_count', 0)} errored."
            )
            if applied.get("error_count"):
                result["ok"] = False
        elif not self.auto_post:
            result["summary"] = "POST plan ready (auto_post disabled; use project_writeback to apply)."
        elif not plan.get("applicable"):
            result["summary"] = f"POST plan not applicable: {plan.get('reason') or plan.get('status') or 'unknown'}"
        self._emit(
            goal.session_id,
            "goal_post_completed",
            {
                "goal_id": goal.goal_id,
                "plan_status": plan.get("status"),
                "plan_files": [
                    op.get("file")
                    for op in plan.get("operations", [])
                    if isinstance(op, dict) and op.get("file")
                ],
                "applied": result.get("applied") if isinstance(result.get("applied"), dict) else None,
            },
        )
        return result

    def _project_control_for(
        self, goal: GoalRun, due_items: List[Dict[str, Any]]
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Build the project_control / project_state pair the writeback planner needs.

        A user-supplied builder wins (the agent layer usually has the full
        project_control snapshot). When no builder is configured, GoalLoop
        derives a minimal, truthful control summary from the goal itself so
        POST still produces an evidence-grade record.
        """
        if self.project_control_builder is not None:
            try:
                result = self.project_control_builder(goal) or {}
                if isinstance(result, dict) and "project_control" in result:
                    control = result.get("project_control") or {}
                    state = result.get("project_state") or {}
                    return (control if isinstance(control, dict) else {}), (
                        state if isinstance(state, dict) else {}
                    )
            except Exception:
                pass
        # Derived control: truthful minimal record built from the goal.
        derived_status = "completed" if goal.status == "completed" else goal.status
        issues: List[str] = []
        for run in goal.stages:
            review = run.review if isinstance(run.review, dict) else {}
            for issue in review.get("issues", []) or []:
                issues.append(f"{run.stage}: {issue}")
        control = {
            "status": derived_status,
            "current_focus": goal.task,
            "next_action": (
                "Continue to next goal or task; POST memory updates applied."
                if derived_status == "completed"
                else "Investigate stage-level issues before next goal."
            ),
            "verification": {
                "status": "ready" if not issues else "partial",
                "rule": "GoalLoop POST builds the plan; apply only when status==ready.",
            },
            "required_gates": ["POST"],
            "pending_gates": [] if not issues else ["POST"],
            "blockers": [],
            "memory_updates_due": due_items,
            "truthfulness": {
                "rule": "Strong claims require evidence; POST writes carry a session-scoped idempotency marker."
            },
        }
        state = {
            "session_id": goal.session_id,
            "goal_id": goal.goal_id,
            "task": goal.task,
            "next_action": control["next_action"],
        }
        return control, state

    def _review_stage(self, stage: str, output: Dict[str, Any]) -> StageReview:
        issues: List[str] = []
        if output.get("ok") is False:
            issues.append(str(output.get("summary") or f"{stage} returned ok=false"))
        if stage == "UNDERSTAND" and not output.get("confirmed"):
            return StageReview("blocked", issues or ["UNDERSTAND was not confirmed."], {"blocked_stage": stage})
        if stage == "CONFIRM" and not output.get("confirmed"):
            return StageReview("blocked", issues or ["CONFIRM was not approved."], {"blocked_stage": stage})
        verdict = "pass" if not issues else "needs_fix"
        return StageReview(verdict, issues, self._next_input_from_output(stage, output))

    def _recall_skill_packs(self, task: str) -> List[Any]:
        """Best-effort lookup of project-side skill packs for ``task``.

        Lazy-imported so the goal loop keeps working when the
        ``skill_packs`` module is not available (e.g. in legacy
        tests). Returns an empty list on any failure. The pack
        directory lives under ``self.artifacts_root`` so tests
        can redirect it via the ``artifacts_root`` constructor arg
        or the ``TTMEVOLVE_GOAL_ARTIFACTS_ROOT`` env var.
        """
        try:
            from agent.skill_packs.bootstrap import get_or_create_registry
        except Exception:
            return []
        try:
            # ``get_or_create_registry`` accepts a project_root; for
            # skill packs the storage path is derived from the
            # *artifacts_root*. We pass artifacts_root as the
            # project_root param so seeds land in the right place.
            registry = get_or_create_registry(self.artifacts_root)
        except Exception:
            return []
        try:
            return registry.recall_for_task(task, limit=3)
        except Exception:
            return []

    def _update_feature_state(self, goal: GoalRun) -> Dict[str, Any]:
        """Open or advance a feature for the goal and refresh the
        PM-style sprint board. Returns a small summary dict so the
        POST stage can include it in the evidence.

        The feature is keyed by a slug derived from the goal task
        so subsequent goal runs against the same task land on the
        same feature and the state machine accumulates progress.
        """
        try:
            from agent.feature_state import (
                FeatureLedger,
                FeatureState,
                FeatureStateError,
                render_progress_md,
            )
        except Exception as exc:
            return {"ok": False, "error": f"feature_state unavailable: {exc}"}
        try:
            ledger = FeatureLedger(self.project_root)
        except Exception as exc:
            return {"ok": False, "error": f"could not open ledger: {exc}"}
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", (goal.task or "").lower()).strip("-")[:48] or goal.goal_id
        feature_id = f"feat-{slug}"
        feature = None
        try:
            feature = ledger.get(feature_id)
        except Exception:
            feature = None
        if feature is None:
            try:
                feature = ledger.open(
                    title=(goal.task or goal.goal_id)[:80],
                    description=goal.task,
                    priority="P1",
                    owner="pm",
                    feature_id=feature_id,
                )
            except FeatureStateError as exc:
                return {"ok": False, "error": str(exc)}
        try:
            ledger.attach_goal(feature_id, goal.goal_id)
        except Exception:
            pass
        # Decide the next state from the goal's outcome. The PM
        # never auto-skips a human review: BLOCKED is the safe
        # default when the goal did not complete. The PM walks
        # the lifecycle (proposed -> approved -> in_progress ->
        # shipped) so the state machine stays consistent.
        try:
            if goal.status == "blocked":
                ledger.transition(
                    feature_id,
                    FeatureState.BLOCKED,
                    reason="; ".join(self._collect_blocked_reasons(goal)) or "goal blocked",
                )
            elif goal.status == "completed":
                if feature.state == FeatureState.PROPOSED:
                    ledger.transition(feature_id, FeatureState.APPROVED)
                if feature.state == FeatureState.APPROVED:
                    ledger.transition(feature_id, FeatureState.IN_PROGRESS)
                if goal.artifacts:
                    ledger.transition(
                        feature_id, FeatureState.SHIPPED,
                        note=f"shipped via {goal.goal_id}",
                    )
            elif goal.status == "running" and feature.state == FeatureState.PROPOSED:
                ledger.transition(feature_id, FeatureState.APPROVED)
                ledger.transition(feature_id, FeatureState.IN_PROGRESS)
        except FeatureStateError:
            pass
        # Refresh the on-disk artefacts so a human operator can
        # see the latest state without opening the ledger. The
        # paths come from ``self.paths`` so tests can redirect
        # them to a tmp dir via ``artifacts_root``.
        try:
            self.paths["sprint_board_md"].write_text(
                ledger.sprint_board(), encoding="utf-8",
            )
            self.paths["progress_md"].write_text(
                render_progress_md(ledger.list_features()), encoding="utf-8",
            )
        except Exception:
            pass
        latest = ledger.get(feature_id)
        return {
            "ok": True,
            "feature_id": feature_id,
            "state": latest.state.value if latest else "unknown",
        }

    def _collect_blocked_reasons(self, goal: GoalRun) -> List[str]:
        reasons: List[str] = []
        for run in goal.stages:
            review = run.review if isinstance(run.review, dict) else {}
            for issue in review.get("issues") or []:
                reasons.append(f"{run.stage}: {issue}")
        return reasons[:8]

    def _coerce_subgoal_specs(
        self, raw: Any, goal: GoalRun,
    ) -> List[Any]:
        """Normalize the LLM's ``sub_goals`` output into a list of
        ``SubGoalSpec``. Accepts the new structured form (list of
        dicts with type / depends_on / acceptance) and the legacy
        plain-string form. Legacy entries are wrapped as
        ``code`` sub-goals so existing tests keep working."""
        from agent.goal_dag import (
            DEFAULT_TYPE_HINT,
            KNOWN_HINTS,
            SubGoalSpec,
            SubGoalType,
        )
        if not isinstance(raw, list):
            return []
        out: List[SubGoalSpec] = []
        for index, item in enumerate(raw[: self.max_subgoals]):
            if isinstance(item, str):
                out.append(SubGoalSpec(
                    sub_id=f"sub-{index + 1}",
                    task=item,
                    type=SubGoalType.CODE,
                ))
                continue
            if not isinstance(item, dict):
                continue
            sub_id = str(item.get("id") or item.get("sub_id") or f"sub-{index + 1}")
            type_str = str(item.get("type") or SubGoalType.CODE.value)
            try:
                sub_type = SubGoalType(type_str)
            except ValueError:
                sub_type = SubGoalType.CODE
            hint = str(item.get("model_hint") or DEFAULT_TYPE_HINT.get(sub_type, "balanced"))
            if hint not in KNOWN_HINTS:
                hint = "balanced"
            out.append(SubGoalSpec(
                sub_id=sub_id,
                task=str(item.get("task") or sub_id),
                type=sub_type,
                depends_on=self._string_list(item.get("depends_on")),
                acceptance=self._string_list(item.get("acceptance")),
                model_hint=hint,
                assigned_agent=str(item.get("assigned_agent") or ""),
                artifacts_expected=self._string_list(item.get("artifacts_expected")),
                metadata=dict(item.get("metadata") or {}) if isinstance(item.get("metadata"), dict) else {},
            ))
        return out

    def _user_supplied_subgoal_runner(self) -> Optional[SubGoalRunner]:
        """Return the user-supplied sub-goal runner, or ``None`` if
        the default one is in use. The legacy interface takes a
        list of plain task strings; the new typed DAG path bypasses
        the runner entirely."""
        runner = self.sub_goal_runner
        if runner is None:
            return None
        # Bound methods are equal by their underlying function, not
        # by object identity (each ``self.method`` access returns a
        # fresh bound-method object). Compare by ``__func__`` to
        # detect the default runner.
        default_func = getattr(self._default_sub_goal_runner, "__func__", None)
        if default_func is not None and getattr(runner, "__func__", None) is default_func:
            return None
        return runner

    def _run_legacy_subgoal_runner(
        self,
        runner: SubGoalRunner,
        tasks: List[str],
        goal: GoalRun,
    ) -> List[Dict[str, Any]]:
        """Call a user-supplied sub-goal runner with the legacy
        ``(tasks, session_id, parent_depth)`` signature. Mirrors the
        original behaviour so existing tests and integrations keep
        working."""
        if not tasks:
            return []
        self._emit(
            goal.session_id,
            "goal_sub_goals_started",
            {
                "goal_id": goal.goal_id,
                "depth": goal.depth,
                "tasks": tasks,
            },
        )
        try:
            results = runner(tasks, goal.session_id, goal.depth) or []
        except Exception as exc:
            results = [
                {
                    "goal_id": "runner-error",
                    "task": "<runner>",
                    "status": "failed",
                    "summary": f"sub_goal_runner crashed: {exc}"[:400],
                }
            ]
        for sub in results:
            if not isinstance(sub, dict):
                continue
            sub.setdefault("parent_goal_id", goal.goal_id)
        self._emit(
            goal.session_id,
            "goal_sub_goals_completed",
            {
                "goal_id": goal.goal_id,
                "depth": goal.depth,
                "results": list(results),
            },
        )
        return [sub for sub in results if isinstance(sub, dict)]

    def _run_subgoal_dag(
        self, specs: List[Any], goal: GoalRun,
    ) -> List[Dict[str, Any]]:
        """Schedule the parent goal's sub-goals through the typed
        DAG. Emits start / completion events so the Evidence Bundle
        shows parallel execution. If the LLM did not include an
        integration sub-goal, one is appended that depends on every
        upstream sub-goal.
        """
        from agent.goal_dag import (
            GoalDAGScheduler,
            SubGoalSpec,
            SubGoalType,
        )
        from agent.typed_subloop import build_default_runners
        runners = build_default_runners(dev_runner=self.dev_runner)
        scheduler = GoalDAGScheduler(
            runners,
            max_concurrent=self.max_concurrent_subgoals,
        )
        specs = list(specs)
        if specs and not any(spec.type == SubGoalType.INTEGRATION for spec in specs):
            specs.append(SubGoalSpec(
                sub_id="integration",
                task=f"Integrate {len(specs)} upstream sub-goal(s) into the parent deliverable",
                type=SubGoalType.INTEGRATION,
                depends_on=[s.sub_id for s in specs],
            ))
        self._emit(
            goal.session_id,
            "goal_sub_goals_started",
            {
                "goal_id": goal.goal_id,
                "depth": goal.depth,
                "sub_goals": [s.to_dict() for s in specs],
            },
        )
        try:
            results = scheduler.run(
                specs,
                parent_goal_id=goal.goal_id,
                parent_session_id=goal.session_id,
            )
        except Exception as exc:
            self._emit(
                goal.session_id,
                "goal_sub_goals_failed",
                {
                    "goal_id": goal.goal_id,
                    "error": str(exc)[:400],
                },
            )
            return []
        serialized = [r.to_dict() for r in results]
        self._emit(
            goal.session_id,
            "goal_sub_goals_completed",
            {
                "goal_id": goal.goal_id,
                "depth": goal.depth,
                "results": serialized,
            },
        )
        return serialized

    def _compile_handoff(
        self,
        goal: GoalRun,
        from_stage: str,
        to_stage: str,
        output: Dict[str, Any],
        review: StageReview,
    ) -> StageHandoff:
        return StageHandoff(
            from_stage=from_stage,
            to_stage=to_stage,
            goal_id=goal.goal_id,
            summary=str(output.get("summary") or f"{from_stage} completed."),
            data=review.next_input,
        )

    def _next_input_from_output(self, stage: str, output: Dict[str, Any]) -> Dict[str, Any]:
        allowed_keys = {
            "UNDERSTAND": ["summary", "subtasks", "success_criteria", "confirmed"],
            "DOC_READ": ["summary", "docs"],
            "RESEARCH": ["summary", "constraints", "risks", "memory_boundary"],
            "PROPOSE": ["summary", "proposal", "sub_goal_results", "recursive_allowed"],
            "CONFIRM": ["summary", "confirmed", "artifacts"],
            "DEV": ["summary", "dev_result"],
            "BUILD": ["summary", "status", "ok", "returncode", "stderr_tail"],
            "REV": ["summary", "issues", "intent_match"],
            "REPORT": ["summary", "report"],
            "POST": ["summary", "memory_updates_due"],
        }.get(stage, ["summary"])
        return {key: output.get(key) for key in allowed_keys if key in output}

    def _docs_context(self, docs: List[Dict[str, Any]]) -> str:
        blocks = []
        for doc in docs[:6]:
            excerpt = str(doc.get("excerpt") or "")[:800]
            blocks.append(f"### {doc.get('path')}\n{excerpt}")
        return "Loaded project documents:\n" + "\n\n".join(blocks) if blocks else ""

    def _rev_context(self, goal: GoalRun, handoff: StageHandoff) -> str:
        lines = [f"Stages executed: {len(goal.stages)}/{len(GOAL_STAGES)}"]
        dev_summary = handoff.data.get("summary")
        if dev_summary:
            lines.append(f"Latest stage summary: {str(dev_summary)[:400]}")
        if goal.artifacts:
            lines.append("Artifacts: " + ", ".join(str(a.get("path")) for a in goal.artifacts[:6]))
        return "\n".join(lines)

    def _request_confirmation(
        self,
        goal: GoalRun,
        *,
        stage: str,
        title: str,
        message: str,
        strength: str,
    ) -> bool:
        confirmation_id = f"{goal.goal_id}-{stage.lower()}-{uuid.uuid4().hex[:6]}"
        auto = self.approval_policy == "never" or self.confirm is None
        self._emit(
            goal.session_id,
            "goal_confirmation_requested",
            {
                "goal_id": goal.goal_id,
                "stage": stage,
                "confirmation_id": confirmation_id,
                "title": title,
                "message": message,
                "strength": strength,
                "auto_confirmed": auto,
            },
        )
        if auto:
            return True
        try:
            return bool(self.confirm(message))
        except Exception:
            return False

    def _write_confirm_artifacts(self, goal: GoalRun, proposal: Dict[str, Any]) -> List[Dict[str, Any]]:
        today = datetime.now().strftime("%Y-%m-%d")
        slug = self._slug(goal.task) or goal.goal_id
        # Write CONFIRM artifacts under ``artifacts_root`` so tests
        # can redirect them. The path that lands in the artifacts
        # list is the project-relative form (when applicable) so
        # the evidence surface stays stable.
        contract_dir = self.paths["system_contracts_goals"]
        decision_dir = self.paths["decisions"]
        contract_filename = f"{goal.goal_id}.md"
        decision_filename = f"{today}-{slug}.md"
        contract_path = contract_dir / contract_filename
        decision_path = decision_dir / decision_filename
        contract_text = self._contract_markdown(goal, proposal)
        decision_text = self._decision_markdown(goal, proposal, today)
        artifacts: List[Dict[str, Any]] = []
        for path, text, kind, rel in [
            (contract_path, contract_text, "system_contract", f"system-contracts/goals/{contract_filename}"),
            (decision_path, decision_text, "decision", f"decisions/{decision_filename}"),
        ]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            artifacts.append({"kind": kind, "path": rel.replace("\\", "/")})
        return artifacts

    def _contract_markdown(self, goal: GoalRun, proposal: Dict[str, Any]) -> str:
        return "\n".join(
            [
                f"# Goal Contract: {goal.goal_id}",
                "",
                f"- goal_id: `{goal.goal_id}`",
                f"- session_id: `{goal.session_id}`",
                f"- status: `confirmed`",
                f"- depth: `{goal.depth}`",
                f"- task: {goal.task}",
                "",
                "## Recommended Approach",
                str(proposal.get("recommended") or "Use GoalLoop stage contract."),
                "",
                "## Acceptance",
                *[f"- {item}" for item in proposal.get("acceptance", [])],
                "",
                "## Runtime Rules",
                "- DEV must not start until CONFIRM writes this contract.",
                "- Stage handoff is the only supported input to the next stage.",
                "- Recursive sub-goals are allowed only in PROPOSE, DEV, and REV.",
                "",
            ]
        )

    def _decision_markdown(self, goal: GoalRun, proposal: Dict[str, Any], today: str) -> str:
        return "\n".join(
            [
                f"# Decision: GoalLoop For {goal.goal_id}",
                "",
                f"- date: `{today}`",
                "- status: `accepted`",
                f"- session_id: `{goal.session_id}`",
                "",
                "## Context",
                f"Task: {goal.task}",
                "",
                "## Decision",
                str(proposal.get("recommended") or "Run the task through GoalLoop."),
                "",
                "## Risks",
                *[f"- {item}" for item in proposal.get("risks", [])],
                "",
                "## Alternatives",
                *[f"- {item}" for item in proposal.get("alternatives", [])],
                "",
            ]
        )

    def _final_report(self, goal: GoalRun) -> str:
        lines = [
            "# GoalLoop Report",
            "",
            f"- goal_id: `{goal.goal_id}`",
            f"- status: `{goal.status}`",
            f"- stages: `{len(goal.stages)}/{len(GOAL_STAGES)}`",
        ]
        if goal.artifacts:
            lines.append(f"- artifacts: `{len(goal.artifacts)}`")
        if goal.sub_goals:
            lines.append(f"- sub_goals: `{len(goal.sub_goals)}`")
        issues = []
        for run in goal.stages:
            review = run.review if isinstance(run.review, dict) else {}
            for issue in review.get("issues", []) or []:
                issues.append(f"{run.stage}: {issue}")
        lines.extend(["", "## Stage Results"])
        for run in goal.stages:
            summary = run.output.get("summary") if isinstance(run.output, dict) else ""
            lines.append(f"- {run.stage}: `{run.status}` {summary or ''}".rstrip())
        if goal.artifacts:
            lines.extend(["", "## Artifacts"])
            for artifact in goal.artifacts:
                lines.append(f"- `{artifact.get('path')}`")
        if goal.sub_goals:
            lines.extend(["", "## Sub-Goals"])
            for sub in goal.sub_goals:
                lines.append(
                    f"- `{sub.get('status', 'unknown')}` {sub.get('task', '')} "
                    f"→ {sub.get('summary', '')}".rstrip()
                )
        if issues:
            lines.extend(["", "## Issues", *[f"- {issue}" for issue in issues]])
        return "\n".join(lines)

    def _compact_dev_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        compact = {
            "done": result.get("done"),
            "output": str(result.get("output") or "")[:1200],
            "iteration_count": result.get("iteration_count"),
            "trajectory_steps": len(result.get("trajectory", [])) if isinstance(result.get("trajectory"), list) else 0,
            "cancelled": result.get("cancelled"),
            "error": result.get("error"),
        }
        # Forward caller-defined side-channel fields (any `_foo` key) so
        # harnesses like MultiAgentRunner can carry insights through the loop
        # without rewriting the compact contract.
        for key, value in result.items():
            if key.startswith("_") and key not in compact:
                compact[key] = value
        return compact

    def _permissions_for(self, stage: str) -> Dict[str, Any]:
        return {
            "read_only": stage in READ_ONLY_STAGES,
            "contract_writes_only": stage in CONTRACT_WRITE_STAGES,
            "side_effects_allowed": stage in SIDE_EFFECT_STAGES,
        }

    def _stage_payload(self, goal: GoalRun, stage_run: StageRun) -> Dict[str, Any]:
        return {
            "goal_id": goal.goal_id,
            "session_id": goal.session_id,
            "task": goal.task,
            "status": goal.status,
            "current_stage": goal.current_stage,
            "stage": stage_run.stage,
            "stage_run": asdict(stage_run),
            "progress": self._progress(goal),
        }

    def _goal_payload(self, goal: GoalRun) -> Dict[str, Any]:
        return {
            "version": GOAL_LOOP_VERSION,
            "goal_id": goal.goal_id,
            "session_id": goal.session_id,
            "task": goal.task,
            "status": goal.status,
            "current_stage": goal.current_stage,
            "depth": goal.depth,
            "budget": dict(goal.budget),
            "created_at": goal.created_at,
            "stages": [asdict(stage) for stage in goal.stages],
            "artifacts": list(goal.artifacts),
            "sub_goals": list(goal.sub_goals),
            "progress": self._progress(goal),
        }

    def _progress(self, goal: GoalRun) -> Dict[str, Any]:
        counts = {"pending": 0, "running": 0, "done": 0, "needs_fix": 0, "blocked": 0}
        for run in goal.stages:
            counts[run.status] = counts.get(run.status, 0) + 1
        return {
            "stage_order": list(GOAL_STAGES),
            "completed": counts.get("done", 0),
            "total": len(GOAL_STAGES),
            "counts": counts,
        }

    def _trajectory_step(self, index: int, run: StageRun) -> Dict[str, Any]:
        return {
            "iteration": index,
            "step_id": run.stage,
            "action": {"tool": f"goal_stage:{run.stage}", "params": {"stage": run.stage}},
            "observation": {
                "ok": run.status not in {"blocked"},
                "stage": run.stage,
                "review": run.review,
            },
            "output": run.output,
        }

    def _safe_project_path(self, rel_path: Path) -> Path:
        path = (self.project_root / rel_path).resolve()
        root = self.project_root.resolve()
        if root not in [path, *path.parents]:
            raise GoalLoopError(f"refusing to write outside project root: {rel_path}")
        return path

    @staticmethod
    def _goal_id(session_id: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(session_id or "")).strip("-")
        return f"goal-{safe or uuid.uuid4().hex[:8]}"

    @staticmethod
    def _slug(text: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "").lower()).strip("-")
        return slug[:64].strip("-")

    @staticmethod
    def _string_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        out = []
        for item in value:
            text = str(item).strip()
            if text:
                out.append(text)
        return out

    @staticmethod
    def _subtasks(task: str) -> List[str]:
        parts = [
            item.strip(" -\t\r\n")
            for item in re.split(r"\n+|(?:\d+\.)|[;；]", task)
            if item.strip(" -\t\r\n")
        ]
        if len(parts) <= 1:
            return [
                "Confirm intent and success criteria.",
                "Load required project documents.",
                "Research current code and constraints.",
                "Implement, verify, review, and report.",
            ]
        return parts[:8]

    @staticmethod
    def _next_stage(stage: str) -> str:
        try:
            idx = GOAL_STAGES.index(stage)
        except ValueError:
            return ""
        if idx + 1 >= len(GOAL_STAGES):
            return ""
        return GOAL_STAGES[idx + 1]

    def _check_cancelled(self) -> None:
        if self.cancel_check and self.cancel_check():
            from core.cancellation import TaskCancelled

            raise TaskCancelled()

    def _emit(self, session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        if not self.emit:
            return
        self.emit(
            {
                "type": event_type,
                "session_id": session_id,
                "source": "goal_loop",
                "payload": payload,
            }
        )
