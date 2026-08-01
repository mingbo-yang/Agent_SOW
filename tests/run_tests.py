from __future__ import annotations

import tempfile
import inspect
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_openjiuwen_core import (
    test_challenge_dataset_selects_domain_balanced_tasks,
    test_fault_profile_and_recovery_tool,
    test_key_step_f1_score,
    test_openjiuwen_baseline_and_enhanced_tool_sets,
    test_openjiuwen_full_enhanced_exposes_only_recovery_tools,
    test_openjiuwen_runner_repeats_to_limit_with_unique_ids,
    test_openjiuwen_runner_selects_domain_balanced_tasks,
    test_retrieve_skills_returns_skill_plan,
)
from tests.test_agentbench import (
    test_agentbench_adapter_fallback_task_shape,
    test_agentbench_auto_finalize_submits_last_answer,
    test_agentbench_db_tool_sets,
    test_agentbench_db_tools_record_expected_steps,
    test_agentbench_enhanced_abstains_without_validated_db_skill,
    test_agentbench_runner_generates_mock_result_json,
    test_agentbench_runner_prefers_submitted_answer,
    test_agentbench_submitter_preserves_exact_scalar_result,
    test_agentbench_sql_fixture_execution,
)
from tests.test_skills_graph import test_skill_extraction_store_and_graph
from tests.test_tracing import test_trace_recorder_jsonl_roundtrip


def main() -> None:
    tests = [
        test_trace_recorder_jsonl_roundtrip,
        test_skill_extraction_store_and_graph,
        test_openjiuwen_runner_selects_domain_balanced_tasks,
        test_openjiuwen_runner_repeats_to_limit_with_unique_ids,
        test_challenge_dataset_selects_domain_balanced_tasks,
        test_openjiuwen_baseline_and_enhanced_tool_sets,
        test_openjiuwen_full_enhanced_exposes_only_recovery_tools,
        test_fault_profile_and_recovery_tool,
        test_retrieve_skills_returns_skill_plan,
        test_key_step_f1_score,
        test_agentbench_adapter_fallback_task_shape,
        test_agentbench_auto_finalize_submits_last_answer,
        test_agentbench_submitter_preserves_exact_scalar_result,
        test_agentbench_enhanced_abstains_without_validated_db_skill,
        test_agentbench_db_tool_sets,
        test_agentbench_sql_fixture_execution,
        test_agentbench_db_tools_record_expected_steps,
        test_agentbench_runner_generates_mock_result_json,
        test_agentbench_runner_prefers_submitted_answer,
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
