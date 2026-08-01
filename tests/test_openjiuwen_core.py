from knowledge_agent.evaluation.openjiuwen_runner import OpenJiuwenEvaluationRunner
from knowledge_agent.evaluation.result import key_step_f1_score
from knowledge_agent.graph.skill_graph import SkillGraph
from knowledge_agent.openjiuwen_agent.tools import OpenJiuwenRunContext, build_openjiuwen_tools
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
    assert "retrieve_skills" in enhanced_names
    assert "update_skill_feedback" in enhanced_names


def test_key_step_f1_score():
    assert key_step_f1_score(["extract_claim", "check_policy"], ["extract_claim", "check_policy"]) == 1.0
    assert key_step_f1_score(["extract_claim"], ["extract_claim", "check_policy"]) < 1.0
