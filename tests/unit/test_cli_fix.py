"""`patchloop fix` (SPEC §10, decisions 29 and 30): fakes for the engine, the model and Docker."""

import hashlib
from pathlib import Path

import pytest
from support.projects import make_buggy_project
from typer.testing import CliRunner

from patchloop.cli import app, describe_step
from patchloop.environment import CheckItem
from patchloop.llm.client import FakeLLMClient, LLMError
from patchloop.runs import load_record
from patchloop.schemas import GeneratedTest, Patch, RunResult

runner = CliRunner()
DIFF = (
    "--- a/pkg/calc.py\n+++ b/pkg/calc.py\n@@ -1,2 +1,2 @@\n"
    "-    return a - b\n+    return a + b\n"
)
FIXED = RunResult(
    status="fixed", best_attempt=0, diff=DIFF, explanation="add must add", stop_reason="success"
)


class Calls:
    def __init__(self):
        self.args = None


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Environment is fine; the engine is replaced by `result`; records go to tmp_path/runs."""
    project = make_buggy_project(tmp_path / "proj")
    runs_dir = tmp_path / "runs"
    config = tmp_path / "patchloop.yml"
    config.write_text(f"runs_dir: {runs_dir}\n", encoding="utf-8")
    calls = Calls()
    state = {"result": FIXED, "steps": [], "error": None}

    def fake_run_fix(project_path, cfg, llm, docker, issue=None, **overrides):
        calls.args = (project_path, issue)
        for step in state["steps"]:
            overrides["on_step"](*step)
        if state["error"]:
            raise state["error"]
        return state["result"]

    monkeypatch.setattr("patchloop.cli.run_checks", lambda cfg: [CheckItem("Docker", True, "ok")])
    monkeypatch.setattr("patchloop.cli.build_clients", lambda cfg: (FakeLLMClient([]), object()))
    monkeypatch.setattr("patchloop.cli.run_fix", fake_run_fix)

    def invoke(*extra, project_arg=None):
        args = ["fix", str(project_arg or project), "--config", str(config), *extra]
        return runner.invoke(app, args)

    invoke.project, invoke.runs_dir, invoke.calls, invoke.state = project, runs_dir, calls, state
    return invoke


def saved_ids(runs_dir):
    return [p.name for p in runs_dir.iterdir()] if runs_dir.exists() else []


def test_a_fixed_run_shows_the_diff_the_explanation_and_the_run_id_and_saves_a_record(setup):
    result = setup("--issue", "add() is wrong")
    assert result.exit_code == 0, result.output
    (run_id,) = saved_ids(setup.runs_dir)
    assert "+    return a + b" in result.output and "add must add" in result.output
    assert run_id in result.output and f"patchloop apply {run_id}" in result.output
    record = load_record(setup.runs_dir, run_id)
    assert record.result == FIXED and record.issue == "add() is wrong"
    assert record.project == str(setup.project.resolve())
    assert setup.calls.args == (setup.project, "add() is wrong")


def test_a_partial_fix_is_labelled_and_exits_one(setup):
    setup.state["result"] = RunResult(
        status="partially_fixed", best_attempt=0, diff=DIFF, stop_reason="iteration_limit",
        explanation="did half\n\nStill failing:\n- tests/test_calc.py:3 still wrong",
    )
    result = setup()
    assert result.exit_code == 1
    assert "partial" in result.output.lower() and "still wrong" in result.output
    (run_id,) = saved_ids(setup.runs_dir)
    assert f"patchloop apply {run_id}" in result.output  # decision 30: allowed with a warning


@pytest.mark.parametrize(
    ("status", "code", "reason"),
    [("no_bugs_found", 0, "none"), ("not_fixed", 1, "stagnation")],
)
def test_runs_without_a_diff_are_recorded_but_offer_no_apply(setup, status, code, reason):
    setup.state["result"] = RunResult(status=status, stop_reason=reason, explanation="nothing")
    result = setup()
    assert result.exit_code == code
    assert len(saved_ids(setup.runs_dir)) == 1
    assert "patchloop apply" not in result.output


def test_the_generated_test_is_shown_and_marked_as_not_part_of_the_fix(setup):
    test = GeneratedTest(
        path="tests/test_patchloop_generated.py",
        content="def test_repro():\n    assert 1 == 2\n",
        output="tests/x.py:5 assert 1 == 2",
    )
    setup.state["result"] = FIXED.model_copy(update={"generated_test": test})
    out = setup().output
    assert "test_patchloop_generated.py" in out and "def test_repro" in out
    assert "not part of the fix" in out and "assert 1 == 2" in out


def test_progress_lines_arrive_through_on_step(setup):
    setup.state["steps"] = [("prepare", {}), ("fix", {"new_patch": Patch(
        files={"pkg/calc.py": "x"}, explanation="e")})]
    out = setup().output
    assert out.index("image") < out.index("programmer")  # one line per step, in order
    assert "1 file" in out


def test_the_issue_can_come_from_a_file(setup, tmp_path):
    issue = tmp_path / "bug.md"
    issue.write_text("add() subtracts\n", encoding="utf-8")
    assert setup("--issue-file", str(issue)).exit_code == 0
    assert setup.calls.args[1] == "add() subtracts"


def test_both_issue_options_at_once_is_a_usage_error_and_starts_nothing(setup, tmp_path):
    issue = tmp_path / "bug.md"
    issue.write_text("x", encoding="utf-8")
    result = setup("--issue", "a", "--issue-file", str(issue))
    assert result.exit_code == 2 and "either" in result.output
    assert setup.calls.args is None and saved_ids(setup.runs_dir) == []


@pytest.mark.parametrize("content", [None, "", "  \n"])
def test_an_unreadable_or_empty_issue_file_is_an_error(setup, tmp_path, content):
    issue = tmp_path / "bug.md"
    if content is not None:
        issue.write_text(content, encoding="utf-8")
    result = setup("--issue-file", str(issue))
    assert result.exit_code == 2 and "issue" in result.output.lower()
    assert setup.calls.args is None


def test_a_missing_project_is_a_usage_error(setup, tmp_path):
    result = setup(project_arg=tmp_path / "nope")
    assert result.exit_code == 2 and setup.calls.args is None


def test_a_failed_environment_check_starts_no_run(setup, monkeypatch):
    items = [CheckItem("Ollama", False, "not reachable", "start it")]
    monkeypatch.setattr("patchloop.cli.run_checks", lambda cfg: items)
    result = setup()
    assert result.exit_code == 2
    assert "not reachable" in result.output and "start it" in result.output
    assert setup.calls.args is None and saved_ids(setup.runs_dir) == []


def test_an_engine_error_is_a_message_and_exit_two_not_a_traceback(setup):
    setup.state["error"] = LLMError("Ollama timed out")
    result = setup()
    assert result.exit_code == 2 and "Ollama timed out" in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert saved_ids(setup.runs_dir) == []


def test_an_error_text_with_markup_like_brackets_is_still_a_clean_message(setup):
    setup.state["error"] = LLMError("model said [/INST] and [red]x")
    result = setup()
    assert result.exit_code == 2
    assert "[/INST]" in result.output and "[red]x" in result.output


def test_a_runs_dir_inside_the_project_is_refused_before_anything_runs(setup, tmp_path):
    config = tmp_path / "inside.yml"
    config.write_text(f"runs_dir: {setup.project}/runs\n", encoding="utf-8")
    result = runner.invoke(app, ["fix", str(setup.project), "--config", str(config)])
    assert result.exit_code == 2 and "inside the project" in result.output
    assert setup.calls.args is None and not (setup.project / "runs").exists()


def test_the_tester_line_matches_what_the_tester_did():
    test = GeneratedTest(path="tests/t.py", content="c", output="o")
    assert "accepted" in describe_step("tester", {"generated_test": test})
    done = RunResult(status="no_bugs_found")
    assert "nothing found" in describe_step("tester", {"result": done, "route": "finish"})
    assert describe_step("tester", {"stop_reason": "timeout", "route": "finish"}) is None
    assert "without one" in describe_step("tester", {"route": "fix"})


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(str(path.relative_to(root)).encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def test_the_original_project_is_untouched_by_a_real_engine_run(setup, monkeypatch):
    from test_graph import SOURCE, checks

    from patchloop.graph import run_fix as real_run_fix

    rules = {"def add(a, b):\n    return a - b\n": checks(1), "ok": checks(0)}

    def with_fakes(project, cfg, llm, docker, issue=None, **overrides):
        llm = FakeLLMClient([Patch(files={SOURCE: "ok"}, explanation="fix")])
        return real_run_fix(
            project, cfg, llm, docker, issue,
            checks_fn=lambda d, c, p, s, i, work: rules[(work / SOURCE).read_text()],
            image_fn=lambda *a: "img:1",
            **overrides,
        )

    monkeypatch.setattr("patchloop.cli.run_fix", with_fakes)
    before = tree_hash(setup.project)
    result = setup()
    assert result.exit_code == 0, result.output
    assert "+ok" in result.output
    # the real update shapes of the engine produce the progress lines
    assert "original code: build ok, lint ok, tests 1 failing" in result.output
    assert "attempt 1: build ok, lint ok, tests ok" in result.output
    assert "stopping: success" in result.output
    assert tree_hash(setup.project) == before
