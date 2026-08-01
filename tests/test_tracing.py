from knowledge_agent.tracing.recorder import TraceRecorder, load_traces_jsonl


def test_trace_recorder_jsonl_roundtrip(tmp_path):
    recorder = TraceRecorder(tmp_path)
    trace_id = recorder.start("demo task", "ai4science")
    recorder.record_step(
        state="start",
        plan="collect_literature",
        action="collect_literature",
        tool_name="literature_search",
        observation="ok",
    )
    trace = recorder.finish(True, 1.0, "done", key_step_f1=1.0)

    loaded = load_traces_jsonl(tmp_path / "traces.jsonl")
    assert trace.trace_id == trace_id
    assert len(loaded) == 1
    assert loaded[0].steps[0].tool_call.name == "literature_search"
    assert loaded[0].result.success is True

