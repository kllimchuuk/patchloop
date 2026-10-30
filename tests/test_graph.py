import pytest

from patchloop.config import Config, LlmConfig
from patchloop.graph import Engine
from patchloop.llm.client import FakeLLMClient, LiteLLMClient, LLMError
from patchloop.schemas import CheckResult, Failure, Patch

SOURCE = "pkg/calc.py"


def checks(n: int, tag: str = "x", build: bool = True) -> list[CheckResult]:
    """What the checks report for `n` failing tests; `tag` makes the failures distinguishable."""
    fails = [
        Failure(kind="test", file="tests/test_calc.py", line=i + 1, message=f"{tag}{i}")
        for i in range(n)
    ]
    return [
        CheckResult(stage="build", passed=build),
        CheckResult(stage="lint", passed=True),
        CheckResult(stage="tests", passed=n == 0, failures=fails, failing_tests=n),
    ]


class Harness:
    """A project whose check results depend only on the content of pkg/calc.py."""

    def __init__(self, tmp_path, rules, config=None, issue=None, answers=(), llm=None):
        self.project = tmp_path / "proj"
        (self.project / "pkg").mkdir(parents=True)
        (self.project / "tests").mkdir()
        (self.project / "requirements.txt").write_text("", encoding="utf-8")
        (self.project / "tests" / "test_calc.py").write_text(
            "from pkg.calc import add\n\n\ndef test_a():\n    assert add(1, 2) == 3\n"
        )
        (self.project / SOURCE).write_text("bug", encoding="utf-8")
        self.rules, self.issue, self.time = rules, issue, 0.0
        self.llm = llm or FakeLLMClient([self._patch(a) for a in answers])
        self.config = config or Config()
        self.engine = Engine(
            self.project,
            self.config,
            self.llm,
            docker=None,
            clock=lambda: self.time,
            checks_fn=self._checks,
            image_fn=lambda *args: "img:1",
        )

    @staticmethod
    def _patch(content):
        return Patch(files={SOURCE: content}, explanation=f"wrote {content}")

    def _checks(self, docker, config, profile, setup, image, work):
        self.time += 60  # every check run takes a minute of fake time
        return self.rules[(work / SOURCE).read_text(encoding="utf-8")]

    def run(self):
        result = self.engine.run(self.issue)
        assert (self.project / SOURCE).read_text() == "bug"  # the original is never modified
        assert not self.engine.work.exists() and not self.engine.base.exists()
        return result


def test_fixed_on_the_first_attempt(tmp_path):
    h = Harness(tmp_path, {"bug": checks(2), "ok": checks(0)}, answers=["ok"])
    result = h.run()
    assert (result.status, result.stop_reason, result.best_attempt) == ("fixed", "success", 0)
    assert result.reliability == "normal"
    assert "-bug" in result.diff and "+ok" in result.diff
    assert result.explanation == "wrote ok"


def test_fixed_on_the_third_attempt_through_progress(tmp_path):
    rules = {"bug": checks(3), "v1": checks(2, "a"), "v2": checks(1, "b"), "ok": checks(0)}
    result = Harness(tmp_path, rules, answers=["v1", "v2", "ok"]).run()
    assert (result.status, result.best_attempt, result.stop_reason) == ("fixed", 2, "success")


def test_iteration_limit_returns_the_best_attempt_not_the_last(tmp_path):
    rules = {"bug": checks(3), "v1": checks(1, "a"), "v2": checks(5, "b")}
    h = Harness(tmp_path, rules, Config(max_attempts=2), answers=["v1", "v2"])
    result = h.run()
    assert (result.status, result.stop_reason) == ("partially_fixed", "iteration_limit")
    assert result.best_attempt == 0 and "+v1" in result.diff and "v2" not in result.diff
    assert "Still failing:\n- tests/test_calc.py:1 a0" in result.explanation


def test_next_attempt_builds_on_the_best_one_after_a_worse_attempt(tmp_path):
    rules = {"bug": checks(3), "v1": checks(1, "a"), "v2": checks(5, "b"), "ok": checks(0)}
    h = Harness(tmp_path, rules, answers=["v1", "v2", "ok"])
    result = h.run()
    assert (result.status, result.best_attempt) == ("fixed", 2)
    third = h.llm.calls[2][1]["content"]
    assert "### FILE pkg/calc.py (full)\nv1\n" in third  # rolled back to the best attempt's code
    assert "a0" in third and "b0" not in third.split("## Earlier attempts")[0]
    assert "wrote v2" in third  # but the failed attempt stays in the history


def test_a_worse_first_attempt_is_not_a_base_for_the_next(tmp_path):
    rules = {"bug": checks(1), "v1": checks(4, "a"), "ok": checks(0)}
    h = Harness(tmp_path, rules, answers=["v1", "ok"])
    assert h.run().status == "fixed"
    second = h.llm.calls[1][1]["content"]
    assert "### FILE pkg/calc.py (full)\nbug\n" in second  # original code, not v1


def test_stagnation_by_an_identical_patch(tmp_path):
    rules = {"bug": checks(1), "v1": checks(4, "a")}  # worse than the original, so never a base
    result = Harness(tmp_path, rules, answers=["v1", "v1"]).run()
    assert (result.status, result.stop_reason) == ("not_fixed", "stagnation")
    assert result.best_attempt is None and result.diff == ""


def test_stagnation_by_the_same_failures_again(tmp_path):
    rules = {"bug": checks(3), "v1": checks(2, "a"), "v2": checks(2, "a")}
    h = Harness(tmp_path, rules, answers=["v1", "v2", "never used"])
    result = h.run()
    assert (result.status, result.stop_reason, result.best_attempt) == (
        "partially_fixed",
        "stagnation",
        0,
    )
    assert len(h.llm.calls) == 2


def test_timeout_after_an_attempt(tmp_path):
    rules = {"bug": checks(3), "v1": checks(2, "a"), "v2": checks(1, "b")}
    config = Config(loop={"total_timeout_s": 100})
    result = Harness(tmp_path, rules, config, answers=["v1", "v2"]).run()
    assert (result.status, result.stop_reason) == ("partially_fixed", "timeout")
    assert result.best_attempt == 0


def test_no_bugs_found_without_calling_the_model(tmp_path):
    h = Harness(tmp_path, {"bug": checks(0)})
    result = h.run()
    assert (result.status, result.stop_reason) == ("no_bugs_found", "none")
    assert result.best_attempt is None
    assert h.llm.calls == []


def test_an_issue_with_passing_checks_is_a_reduced_reliability_fix(tmp_path):
    rules = {"bug": checks(0), "ok": checks(0)}
    h = Harness(tmp_path, rules, issue="add() is wrong", answers=["ok"])
    result = h.run()
    assert (result.status, result.best_attempt, result.reliability) == ("fixed", 0, "reduced")
    prompt = h.llm.calls[0][1]["content"]
    assert "add() is wrong" in prompt and "### FILE pkg/calc.py (full)" in prompt


def _garbage_client():
    return LiteLLMClient(LlmConfig(), None, lambda **kwargs: "not json")


def test_unusable_answers_spend_attempts_without_crashing(tmp_path):
    h = Harness(tmp_path, {"bug": checks(2)}, Config(max_attempts=2), llm=_garbage_client())
    result = h.run()
    assert (result.status, result.stop_reason, result.best_attempt) == (
        "not_fixed",
        "iteration_limit",
        None,
    )


def test_a_patch_that_changes_nothing_is_a_spent_attempt(tmp_path):
    rules = {"bug": checks(2), "ok": checks(0)}
    h = Harness(tmp_path, rules, answers=["bug", "ok"])  # the first answer repeats the buggy code
    result = h.run()
    assert (result.status, result.best_attempt) == ("fixed", 1)


def test_an_unreachable_model_stops_the_run_and_cleans_up(tmp_path):
    def down(**kwargs):
        raise ConnectionError("down")

    h = Harness(tmp_path, {"bug": checks(2)}, llm=LiteLLMClient(LlmConfig(), None, down))
    with pytest.raises(LLMError):
        h.engine.run(None)
    assert not h.engine.work.exists() and not h.engine.base.exists()
    assert (h.project / SOURCE).read_text() == "bug"


def test_the_largest_attempt_limit_does_not_hit_the_graph_recursion_limit(tmp_path):
    rules = {"bug": checks(20)} | {f"v{i}": checks(20 - i, f"t{i}") for i in range(1, 11)}
    answers = [f"v{i}" for i in range(1, 11)]
    result = Harness(tmp_path, rules, Config(max_attempts=10), answers=answers).run()
    assert (result.status, result.stop_reason, result.best_attempt) == (
        "partially_fixed",
        "iteration_limit",
        9,
    )
