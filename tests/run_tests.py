from __future__ import annotations

import tempfile
import inspect
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_openjiuwen_core import (
    test_key_step_f1_score,
    test_openjiuwen_baseline_and_enhanced_tool_sets,
    test_openjiuwen_runner_selects_domain_balanced_tasks,
)
from tests.test_skills_graph import test_skill_extraction_store_and_graph
from tests.test_tracing import test_trace_recorder_jsonl_roundtrip


def main() -> None:
    tests = [
        test_trace_recorder_jsonl_roundtrip,
        test_skill_extraction_store_and_graph,
        test_openjiuwen_runner_selects_domain_balanced_tasks,
        test_openjiuwen_baseline_and_enhanced_tool_sets,
        test_key_step_f1_score,
    ]
    for test in tests:
        with tempfile.TemporaryDirectory() as tmp:
            if inspect.signature(test).parameters:
                test(Path(tmp))
            else:
                test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
