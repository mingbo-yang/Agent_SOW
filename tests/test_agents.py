from knowledge_agent.graph.skill_graph import SkillGraph
from knowledge_agent.planner.agent import BaselineAgent, KnowledgeEnhancedAgent
from knowledge_agent.skills.extractor import SkillExtractor
from knowledge_agent.skills.store import SkillStore
from knowledge_agent.tracing.recorder import load_traces_jsonl


def test_enhanced_agent_improves_on_seed_task(tmp_path):
    traces = load_traces_jsonl("datasets/seed_traces.jsonl")
    skills = SkillExtractor().extract_from_traces(traces)
    store = SkillStore(tmp_path / "skills.json")
    store.save_many(skills)
    graph = SkillGraph.build_from_skills(store.list())
    task = {
        "expected_steps": [
            "collect_literature",
            "extract_variables",
            "validate_inputs",
            "design_protocol",
            "verify_constraints",
            "generate_report",
        ],
        "required_before_report": ["verify_constraints"],
    }

    baseline = BaselineAgent(tmp_path / "baseline").run(
        "Design a reproducible AI4Science experiment from recent papers and constraints.",
        "ai4science",
        task,
    )
    enhanced = KnowledgeEnhancedAgent(graph, store, tmp_path / "enhanced").run(
        "Design a reproducible AI4Science experiment from recent papers and constraints.",
        "ai4science",
        task,
    )
    assert baseline.success is False
    assert enhanced.success is True
    assert enhanced.key_step_f1 > baseline.key_step_f1

