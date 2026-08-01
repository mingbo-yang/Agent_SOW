from demos.run_all import TASKS, build_graph
from knowledge_agent.planner.agent import BaselineAgent, KnowledgeEnhancedAgent


def main() -> None:
    store, graph = build_graph(__import__("pathlib").Path("outputs"))
    task = TASKS[1]
    baseline = BaselineAgent("outputs/traces/finance_baseline").run(task["task"], task["domain"], task)
    enhanced = KnowledgeEnhancedAgent(graph, store, "outputs/traces/finance_enhanced").run(
        task["task"], task["domain"], task
    )
    print({"baseline": baseline.plan, "baseline_success": baseline.success})
    print({"enhanced": enhanced.plan, "enhanced_success": enhanced.success})


if __name__ == "__main__":
    main()

