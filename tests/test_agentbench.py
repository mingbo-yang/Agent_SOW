import asyncio
import json

from knowledge_agent.benchmarks.agentbench_adapter import AgentBenchDBAdapter, execute_sql_fixture
from knowledge_agent.evaluation.agentbench_runner import AgentBenchEvaluationRunner
from knowledge_agent.evaluation.result import AgentRunResult
from knowledge_agent.graph.skill_graph import SkillGraph
from knowledge_agent.openjiuwen_agent.tools import OpenJiuwenRunContext, build_openjiuwen_tools
from knowledge_agent.skills.store import SkillStore
from knowledge_agent.tracing.recorder import TraceRecorder
from knowledge_agent.tracing.schema import ExecutionResult, Observation, ToolCall, Trace, TraceStep


def test_agentbench_adapter_fallback_task_shape(tmp_path):
    adapter = AgentBenchDBAdapter(agentbench_root=tmp_path / "missing", split="dev")
    task = adapter.load_tasks(limit=1)[0]
    assert task["domain"] == "agentbench_db"
    assert task["benchmark_metadata"]["benchmark"] == "AgentBench"
    assert task["benchmark_metadata"]["environment"] == "dbbench"
    assert task["benchmark_metadata"]["official_available"] is False
    assert task["expected_steps"] == [
        "read_schema",
        "generate_sql",
        "execute_sql",
        "validate_answer",
        "submit_answer",
    ]


def test_agentbench_db_tool_sets(tmp_path):
    context = OpenJiuwenRunContext(
        task="Which department has the most employees?",
        domain="agentbench_db",
        trace_recorder=TraceRecorder(tmp_path / "traces"),
        skill_store=SkillStore(tmp_path / "skills.json"),
        skill_graph=SkillGraph(),
    )
    context.start()
    baseline_names = {tool.card.name for tool in build_openjiuwen_tools(context, agent_type="baseline")}
    enhanced_names = {tool.card.name for tool in build_openjiuwen_tools(context, agent_type="enhanced")}
    assert {"db_schema_reader", "sql_query_executor", "answer_submitter"} <= baseline_names
    assert "retrieve_skills" not in baseline_names
    assert enhanced_names == baseline_names
    assert "retrieve_skills" not in enhanced_names
    assert "alternative_tool_selector" not in enhanced_names


def test_agentbench_sql_fixture_execution():
    fixture = {
        "tables": {
            "departments": [{"id": 1, "name": "Engineering"}],
            "employees": [{"id": 1, "name": "Ada", "department_id": 1, "salary": 180000}],
        }
    }
    ok, content, rows = execute_sql_fixture(
        fixture,
        "SELECT d.name FROM departments d JOIN employees e ON e.department_id = d.id",
    )
    assert ok is True
    assert "Engineering" in content
    assert rows[0]["name"] == "Engineering"


def test_agentbench_db_tools_record_expected_steps(tmp_path):
    adapter = AgentBenchDBAdapter(agentbench_root=tmp_path / "missing")
    task = adapter.load_tasks(limit=1)[0]
    context = OpenJiuwenRunContext(
        task=task["task"],
        domain="agentbench_db",
        trace_recorder=TraceRecorder(tmp_path / "traces"),
        skill_store=SkillStore(tmp_path / "skills.json"),
        skill_graph=SkillGraph(),
        raw_context=task,
        expected_steps=task["expected_steps"],
    )
    context.start()
    tools = {tool.card.name: tool for tool in build_openjiuwen_tools(context, agent_type="baseline")}
    asyncio.run(tools["db_schema_reader"].invoke({"query": task["task"]}))
    asyncio.run(tools["sql_query_executor"].invoke({"query": task["task"]}))
    asyncio.run(tools["answer_submitter"].invoke({}))
    assert context.executed_steps == [
        "read_schema",
        "generate_sql",
        "execute_sql",
        "validate_answer",
        "submit_answer",
    ]


def test_agentbench_runner_generates_mock_result_json(tmp_path):
    import knowledge_agent.evaluation.agentbench_runner as runner_module

    class FakeOpenJiuwenAgent:
        @classmethod
        def from_env(cls, **kwargs):
            return cls()

        def run(self, task, domain, context, agent_type):
            trace = Trace(
                trace_id="fake_trace",
                task=task,
                domain=domain,
                result=ExecutionResult(
                    success=True,
                    score=1.0,
                    result='{"final_answer":"Engineering"}',
                    interactions=5,
                    tool_calls=3,
                    key_step_f1=1.0,
                ),
            )
            return AgentRunResult(
                task=task,
                domain=domain,
                success=True,
                score=1.0,
                plan=context["expected_steps"],
                agent_type=agent_type,
                task_id=context["task_id"],
                interactions=5,
                tool_calls=3,
                key_step_f1=1.0,
                trace=trace,
            )

    original = runner_module.OpenJiuwenKnowledgeAgent
    runner_module.OpenJiuwenKnowledgeAgent = FakeOpenJiuwenAgent
    try:
        runner = AgentBenchEvaluationRunner(output_dir=tmp_path, agentbench_root=tmp_path / "missing", limit=1)
        payload = runner.run("baseline")
    finally:
        runner_module.OpenJiuwenKnowledgeAgent = original

    assert payload["metrics"]["task_success_rate"] == 1.0
    assert (tmp_path / "agentbench_db_results_baseline.json").exists()
    stored = json.loads((tmp_path / "agentbench_db_results_baseline.json").read_text(encoding="utf-8"))
    assert stored["results"][0]["benchmark"] == "AgentBench"


def test_agentbench_runner_prefers_submitted_answer(tmp_path):
    import knowledge_agent.evaluation.agentbench_runner as runner_module

    class FakeOpenJiuwenAgent:
        @classmethod
        def from_env(cls, **kwargs):
            return cls()

        def run(self, task, domain, context, agent_type):
            trace = Trace(
                trace_id="fake_trace",
                task=task,
                domain=domain,
                steps=[
                    TraceStep(
                        step_id="step_submit",
                        state="openjiuwen_react:submit_answer",
                        plan="submit_answer",
                        action="submit_answer",
                        tool_call=ToolCall(name="answer_submitter", args={"answer": "Engineering"}),
                        observation=Observation(content=json.dumps({"content": "Engineering"})),
                    )
                ],
                result=ExecutionResult(
                    success=True,
                    score=1.0,
                    result='{"output":"Max iterations reached without completion","result_type":"error"}',
                    interactions=5,
                    tool_calls=3,
                    key_step_f1=1.0,
                ),
            )
            return AgentRunResult(
                task=task,
                domain=domain,
                success=True,
                score=1.0,
                plan=context["expected_steps"],
                agent_type=agent_type,
                task_id=context["task_id"],
                interactions=5,
                tool_calls=3,
                key_step_f1=1.0,
                trace=trace,
            )

    original = runner_module.OpenJiuwenKnowledgeAgent
    runner_module.OpenJiuwenKnowledgeAgent = FakeOpenJiuwenAgent
    try:
        runner = AgentBenchEvaluationRunner(output_dir=tmp_path, agentbench_root=tmp_path / "missing", limit=1)
        payload = runner.run("baseline")
    finally:
        runner_module.OpenJiuwenKnowledgeAgent = original

    result = payload["results"][0]
    assert result["final_answer"] == "Engineering"
    assert "Max iterations" in result["raw_final_answer"]
    assert result["official_success"] is True
