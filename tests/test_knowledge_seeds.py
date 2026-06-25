from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from learning.knowledge_base import KnowledgeBase
from learning.knowledge_seeds import KNOWLEDGE_SEED_VERSION, seed_knowledge_base


def test_seed_knowledge_base_is_idempotent_and_searchable():
    with tempfile.TemporaryDirectory() as tmp:
        kb = KnowledgeBase(
            storage_path=Path(tmp) / "knowledge",
            vector_index_config={"enabled": False, "fallback_to_keyword": True},
        )

        first = seed_knowledge_base(kb)
        second = seed_knowledge_base(kb)

        assert first["version"] == KNOWLEDGE_SEED_VERSION
        assert first["stored"] > 0
        assert second["stored"] == 0
        assert second["skipped"] >= first["stored"]
        hits = kb.search("TAPTAP_MAKER_HOME Maker MCP tools/list", top_k=3)
        assert hits
        assert any("TAPTAP_MAKER_HOME" in item["rule"] for item in hits)


if __name__ == "__main__":
    test_seed_knowledge_base_is_idempotent_and_searchable()
    print("[PASS] knowledge seeds")
