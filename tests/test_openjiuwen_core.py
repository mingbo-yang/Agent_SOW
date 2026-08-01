import asyncio
import json

from knowledge_agent.evaluation.openjiuwen_runner import OpenJiuwenEvaluationRunner
from knowledge_agent.evaluation.result import key_step_f1_score
from knowledge_agent.graph.skill_graph import SkillGraph
from knowledge_agent.openjiuwen_agent.tools import (
    OpenJiuwenRunContext,
    RetrieveSkillsTool,
    build_openjiuwen_tools,
)
from knowledge_agent.skills.schema import SkillSpec
from knowledge_agent.skills.store import SkillStore
from knowledge_agent.tracing.recorder import TraceRecorder


def test_openjiuwen_runner_selects_domain_balanced_tasks(tmp_path):
    runner = OpenJiuwenEvaluationRunner(
        dataset_path="datasets/tasks.jsonl",
        output_dir=tmp_path,
        limit=3,
    )
    tasks = runner._load_tasks()
    assert [task["domain"] for task in tasks] == ["ai4science", "finance", "industrial"]


def test_openjiuwen_runner_repeats_to_limit_with_unique_ids(tmp_path):
    runner = OpenJiuwenEvaluationRunner(
        dataset_path="datasets/challenge_tasks.jsonl",
        output_dir=tmp_path,
        limit=100,
        repeat_to_limit=True,
    )
    tasks = runner._load_tasks()
    task_ids = [task["task_id"] for task in tasks]
    assert len(tasks) == 100
    assert len(set(task_ids)) == 100
    assert tasks[0]["repeat_index"] == 0
    assert tasks[-1]["repeat_index"] > 0


def test_openjiuwen_baseline_and_enhanced_tool_sets(tmp_path):
    context = OpenJiuwenRunContext(
        task="Review reimbursement with duplicate receipts.",
        domain="finance",
        trace_recorder=TraceRecorder(tmp_path / "traces"),
        skill_store=SkillStore(tmp_path / "skills.json"),
        skill_graph=SkillGraph(),
        expected_steps=["extract_claim", "check_policy", "anomaly_check"],
    )
    context.start()
    baseline_tools = build_openjiuwen_tools(context, enhanced=False)
    enhanced_tools = build_openjiuwen_tools(context, enhanced=True)
    baseline_names = {tool.card.name for tool in baseline_tools}
    enhanced_names = {tool.card.name for tool in enhanced_tools}

    assert "retrieve_skills" not in baseline_names
    assert "document_parser" in baseline_names
    assert "retrieve_skills" not in enhanced_names
    assert "update_skill_feedback" not in enhanced_names
    assert enhanced_names == baseline_names


def test_openjiuwen_full_enhanced_exposes_only_recovery_tools(tmp_path):
    context = OpenJiuwenRunContext(
        task="Review missing evidence.",
        domain="finance",
        trace_recorder=TraceRecorder(tmp_path / "traces"),
        skill_store=SkillStore(tmp_path / "skills.json"),
        skill_graph=SkillGraph(),
        expected_steps=["extract_claim", "collect_evidence", "approve_or_reject"],
        expected_recovery_steps=["recover_context"],
        raw_context={
            "fault_profile": {
                "failures": [
                    {
                        "step": "collect_evidence",
                        "error_code": "POLICY_EVIDENCE_REQUIRED",
                        "recoverable_by": ["context_requester", "recover_context"],
                    }
                ]
            }
        },
        knowledge_mode="full",
    )
    context.start()
    names = {tool.card.name for tool in build_openjiuwen_tools(context, agent_type="enhanced")}
    assert "retrieve_skills" not in names
    assert "record_trace_step" not in names
    assert "update_skill_feedback" not in names
    assert "context_requester" in names
    assert "rollback_executor" in names


def test_challenge_dataset_selects_domain_balanced_tasks(tmp_path):
    runner = OpenJiuwenEvaluationRunner(
        dataset_path="datasets/challenge_tasks.jsonl",
        output_dir=tmp_path,
        limit=3,
    )
    tasks = runner._load_tasks()
    assert [task["domain"] for task in tasks] == ["ai4science", "finance", "industrial"]
    assert all(task["fault_profile"]["failures"] for task in tasks)


def test_fault_profile_and_recovery_tool(tmp_path):
    context = OpenJiuwenRunContext(
        task="Review missing evidence.",
        domain="finance",
        trace_recorder=TraceRecorder(tmp_path / "traces"),
        skill_store=SkillStore(tmp_path / "skills.json"),
        skill_graph=SkillGraph(),
        expected_steps=["collect_evidence"],
        expected_recovery_steps=["recover_context"],
        raw_context={
            "fault_profile": {
                "failures": [
                    {
                        "step": "collect_evidence",
                        "error_code": "POLICY_EVIDENCE_REQUIRED",
                        "recoverable_by": ["context_requester", "recover_context"],
                    }
                ]
            }
        },
        knowledge_mode="full",
    )
    context.start()
    tools = {tool.card.name: tool for tool in build_openjiuwen_tools(context, agent_type="enhanced")}
    failed = asyncio.run(tools["evidence_collector"].invoke({"query": "collect evidence"}))
    assert failed["ok"] is False
    assert failed["error_code"] == "POLICY_EVIDENCE_REQUIRED"
    recovered = asyncio.run(tools["context_requester"].invoke({"query": "recover"}))
    assert recovered["ok"] is True
    assert context.unresolved_faults() == []
    assert "recover_context" in context.executed_steps


def test_retrieve_skills_returns_skill_plan(tmp_path):
    skill = SkillSpec.create(
        name="finance_evidence_recovery_skill",
        domain="finance",
        description="Recover missing reimbursement evidence before decision.",
        steps=["extract_claim", "collect_evidence", "approve_or_reject"],
        tools=["document_parser", "evidence_collector", "decision_engine"],
        failure_patterns=["missing evidence", "POLICY_EVIDENCE_REQUIRED"],
        rollback=["recover_context"],
        confidence=0.9,
    )
    store = SkillStore(tmp_path / "skills.json")
    store.save(skill)
    context = OpenJiuwenRunContext(
        task="Review missing evidence.",
        domain="finance",
        trace_recorder=TraceRecorder(tmp_path / "traces"),
        skill_store=store,
        skill_graph=SkillGraph.build_from_skills(store.list()),
        raw_context={
            "risk": "missing evidence",
            "fault_profile": {"failures": [{"step": "collect_evidence", "error_code": "POLICY_EVIDENCE_REQUIRED"}]},
        },
    )
    context.start()
    result = asyncio.run(RetrieveSkillsTool(context).invoke({"task": context.task, "domain": context.domain}))
    payload = json.loads(result["content"])
    assert payload["skill_plan"]["rollback_steps"]
    assert "POLICY_EVIDENCE_REQUIRED" in payload["skill_plan"]["matched_failure_patterns"]


def test_key_step_f1_score():
    assert key_step_f1_score(["extract_claim", "check_policy"], ["extract_claim", "check_policy"]) == 1.0
    assert key_step_f1_score(["extract_claim"], ["extract_claim", "check_policy"]) < 1.0
