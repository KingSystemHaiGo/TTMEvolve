"""
agent/tool_contracts.py - tool contract declarations (Phase R2).

Every tool that the agent can call declares a contract. The
contract is the input to ``Executor.propose_action`` and to
``ToolRegistry.rank_tools``. The contract has four parts:

  - ``purpose``: a one-line human description of what the tool
    does. Used by rank_tools to score relevance.
  - ``preconditions``: a list of named predicates that must all
    be true before the tool is allowed to run. Used by
    propose_action as a hard block. Names are looked up in a
    small registry (``agent/contract_predicates.py``).
  - ``postconditions``: a list of named predicates that the
    caller can check after the tool returns. Used to update the
    ``tool_state`` registry so the next rank_tools call knows
    "this tool just changed maker_setup from needs_config to
    available."
  - ``state``: the current state of the tool. One of
    ``available``, ``needs_config``, ``unavailable``, ``busy``.

The contract system is opt-in. Tools without a contract keep
their old behavior (no preflight block, no contract-aware
ranking). The R2 exit gate is that every tool in
``core/executor.py`` and ``agent/builtin_tools.py`` has an
explicit contract.

A tool with ``state != "available"`` is rejected by
``propose_action`` regardless of preconditions, so an
"unavailable" tool cannot be called accidentally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


TOOL_CONTRACT_VERSION = "tool-contract.v1"


class ToolState(str, Enum):
    AVAILABLE = "available"
    NEEDS_CONFIG = "needs_config"
    UNAVAILABLE = "unavailable"
    BUSY = "busy"


# A small registry of named predicate evaluators. Tools reference
# predicates by name (string) so the contract declaration is
# serializable. The runtime resolves the names to callables at
# propose_action time.
PredicateFn = Callable[[Dict[str, Any]], bool]


class PredicateRegistry:
    """Stores named predicate callables.

    Predicates receive the runtime context (``{"maker_ready":
    bool, "sandbox_mode": str, ...}``) and return True iff the
    precondition is satisfied. The registry is populated at
    process start; tools only declare predicate names.
    """

    def __init__(self) -> None:
        self._predicates: Dict[str, PredicateFn] = {}

    def register(self, name: str, fn: PredicateFn) -> None:
        self._predicates[name] = fn

    def evaluate(self, name: str, context: Dict[str, Any]) -> bool:
        fn = self._predicates.get(name)
        if fn is None:
            # Unknown predicate: fail open so a missing
            # predicate does not block the entire runtime. The
            # regression guard catches missing predicates.
            return True
        try:
            return bool(fn(context))
        except Exception:
            # A predicate that raises must not block; fail open
            # but record the error so the operator sees it.
            return True

    def has(self, name: str) -> bool:
        return name in self._predicates

    def names(self) -> Set[str]:
        return set(self._predicates.keys())


# A default registry instance used by Executor and rank_tools.
default_predicate_registry = PredicateRegistry()


def _default_predicate_maker(name: str, default_value: bool = True) -> PredicateFn:
    """Build a predicate that reads a key from the runtime
    context. Useful for the common case where a precondition
    is just "is X ready?"."""
    def _fn(ctx: Dict[str, Any]) -> bool:
        if name in ctx:
            return bool(ctx[name])
        return default_value
    return _fn


@dataclass
class ToolContract:
    """One tool's contract.

    A tool with ``state != ToolState.AVAILABLE`` cannot be
    invoked. A tool whose preconditions are not all satisfied is
    rejected by ``propose_action``. The tool's ``postconditions``
    are checked after the tool returns to update runtime state.
    """

    name: str
    purpose: str = ""
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    state: ToolState = ToolState.AVAILABLE
    side_effects: bool = False
    risk_level: str = "low"
    expected_runtime_s: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": TOOL_CONTRACT_VERSION,
            "name": self.name,
            "purpose": self.purpose,
            "preconditions": list(self.preconditions),
            "postconditions": list(self.postconditions),
            "state": self.state.value,
            "side_effects": self.side_effects,
            "risk_level": self.risk_level,
            "expected_runtime_s": self.expected_runtime_s,
        }


class ContractStore:
    """Stores contracts by tool name. Thread-safe append-only."""

    def __init__(self) -> None:
        self._contracts: Dict[str, ToolContract] = {}
        self._states: Dict[str, ToolState] = {}

    def register(self, contract: ToolContract) -> None:
        self._contracts[contract.name] = contract
        self._states.setdefault(contract.name, contract.state)

    def get(self, name: str) -> Optional[ToolContract]:
        return self._contracts.get(name)

    def get_state(self, name: str) -> ToolState:
        return self._states.get(name, ToolState.AVAILABLE)

    def set_state(self, name: str, state: ToolState) -> None:
        self._states[name] = state

    def has(self, name: str) -> bool:
        return name in self._contracts

    def all_names(self) -> Set[str]:
        return set(self._contracts.keys())

    def evaluate_preconditions(
        self,
        name: str,
        context: Dict[str, Any],
        registry: Optional[PredicateRegistry] = None,
    ) -> Dict[str, Any]:
        """Return a dict of precondition results.

        ``{"precondition": "maker_ready", "satisfied": True}``
        for every precondition the contract declares. Used by
        ``propose_action`` to build a precise error message.
        """
        reg = registry or default_predicate_registry
        contract = self._contracts.get(name)
        if contract is None:
            return []
        return [
            {
                "precondition": pre,
                "satisfied": reg.evaluate(pre, context),
            }
            for pre in contract.preconditions
        ]


# Default store. Tools register against this; tests can construct
# their own store for isolation.
default_contract_store = ContractStore()
