"""Evidence capture tests (app/evidence.py)."""

import json

from app.evidence import TraceWriter, save_screenshot


def test_trace_writer_creates_the_run_directory(tmp_run):
    TraceWriter(run_id="r1", mode="replay", root=tmp_run)

    assert (tmp_run / "replay" / "r1").is_dir()


def test_trace_writer_appends_one_json_object_per_line(tmp_run):
    tracer = TraceWriter(run_id="r1", mode="replay", root=tmp_run)

    tracer.write("run_start")
    tracer.write("step_start", step_index=0, step_id="goto_login", kind="goto")
    tracer.write("step_ok", step_index=0, step_id="goto_login", duration_ms=42)

    lines = (tmp_run / "replay" / "r1" / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3

    parsed = [json.loads(line) for line in lines]
    assert [entry["event"] for entry in parsed] == ["run_start", "step_start", "step_ok"]
    assert [entry["seq"] for entry in parsed] == [1, 2, 3]
    assert parsed[2]["duration_ms"] == 42
    assert parsed[2]["run_id"] == "r1"
    assert parsed[2]["mode"] == "replay"


def test_trace_writer_defaults_absent_fields_to_none_and_detail_to_empty_dict(tmp_run):
    tracer = TraceWriter(run_id="r1", mode="replay", root=tmp_run)

    tracer.write("run_start")

    line = json.loads(
        (tmp_run / "replay" / "r1" / "trace.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert line["step_id"] is None
    assert line["locator"] is None
    assert line["detail"] == {}
    assert line["level"] == "info"


def test_save_screenshot_writes_a_png_at_the_zero_padded_conventional_path(page, tmp_run):
    page.set_content("<p>hello</p>")
    run_dir = tmp_run / "replay" / "r1"
    run_dir.mkdir(parents=True)

    relative_path = save_screenshot(page, run_dir, step_index=3, step_id="open_savings")

    assert relative_path == "steps/003-open_savings.png"
    saved_file = run_dir / "steps" / "003-open_savings.png"
    assert saved_file.is_file()
    assert saved_file.stat().st_size > 0
