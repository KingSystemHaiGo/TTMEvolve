"""
tests/test_evolution_protocol.py — 自进化协议测试
"""

from __future__ import annotations
import shutil
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.event_log import EventLog
from core.resource_registry import ResourceRegistry
from core.evolution_protocol import EvolutionProtocol


def test_propose_validate_deploy_rollback():
    tmp = Path(tempfile.mkdtemp())
    try:
        event_log = EventLog(tmp / "events.jsonl")
        registry = ResourceRegistry(tmp / "resources")
        protocol = EvolutionProtocol(registry, event_log, tmp / "evolution")

        registry.register(
            resource_id="prompt_v1",
            resource_type="prompt",
            content="baseline prompt",
            source="test_baseline",
        )

        proposal = protocol.propose_change(
            resource_id="prompt_v1",
            resource_type="prompt",
            content="new prompt content",
            reason="improve clarity",
        )
        assert proposal.status == "pending"

        validated = protocol.validate(proposal.proposal_id)
        assert validated.status == "validated"

        deployed = protocol.deploy(proposal.proposal_id)
        assert deployed.status == "deployed"

        resource = registry.get("prompt_v1")
        assert resource is not None
        assert resource.content == "new prompt content"

        rolled = protocol.rollback("prompt_v1")
        assert rolled is not None
        assert rolled["version"].startswith("v")

        latest = registry.get("prompt_v1")
        assert latest is not None
        assert latest.content == "baseline prompt"

        print("[PASS] propose validate deploy rollback")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_propose_validate_deploy_rollback()
    print("[PASS] all evolution protocol tests")
