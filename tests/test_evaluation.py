from knowledge_agent.evaluation.runner import EvaluationRunner


def test_evaluation_runner_outputs_comparison(tmp_path):
    runner = EvaluationRunner(
        dataset_path="datasets/tasks.jsonl",
        seed_trace_path="datasets/seed_traces.jsonl",
        output_dir=tmp_path,
    )
    comparison = runner.run_comparison()
    assert comparison["enhanced"]["success_rate"] >= comparison["baseline"]["success_rate"]
    assert (tmp_path / "eval_report.md").exists()

