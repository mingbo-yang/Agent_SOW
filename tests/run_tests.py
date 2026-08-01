from __future__ import annotations

import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_agents import test_enhanced_agent_improves_on_seed_task
from tests.test_evaluation import test_evaluation_runner_outputs_comparison
from tests.test_skills_graph import test_skill_extraction_store_and_graph
from tests.test_tracing import test_trace_recorder_jsonl_roundtrip


def main() -> None:
    tests = [
        test_trace_recorder_jsonl_roundtrip,
        test_skill_extraction_store_and_graph,
        test_enhanced_agent_improves_on_seed_task,
        test_evaluation_runner_outputs_comparison,
    ]
    for test in tests:
        with tempfile.TemporaryDirectory() as tmp:
            test(Path(tmp))
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
