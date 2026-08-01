from knowledge_agent.graph.skill_graph import SkillGraph
from knowledge_agent.skills.extractor import SkillExtractor
from knowledge_agent.skills.store import SkillStore
from knowledge_agent.tracing.recorder import load_traces_jsonl


def test_skill_extraction_store_and_graph(tmp_path):
    traces = load_traces_jsonl("datasets/seed_traces.jsonl")
    skills = SkillExtractor().extract_from_traces(traces)
    assert skills
    assert any(skill.domain == "ai4science" for skill in skills)

    store = SkillStore(tmp_path / "skills.json")
    store.save_many(skills)
    assert store.list()

    graph = SkillGraph.build_from_skills(store.list())
    matched = graph.retrieve(
        "Design a reproducible AI4Science experiment with constraints",
        "ai4science",
        {},
    )
    assert matched
    assert "verify_constraints" in matched[0].steps

