"""The Tester inside the repair loop (SPEC §3 step 4, §9)."""

from support.fake_completion import ScriptedCompletion
from test_graph import Harness, checks

from patchloop.config import Config, LlmConfig
from patchloop.llm.client import LiteLLMClient
from patchloop.schemas import CheckResult, Failure, Patch, TestPlan

TEST_PATH = "tests/test_patchloop_generated.py"
GOOD_TEST = TestPlan(
    content="from pkg.calc import add\n\n\ndef test_repro():\n    assert add(1, 2) == 3\n",
    explanation="repro",
)
OTHER_TEST = TestPlan(content="def test_other():\n    assert 3 == 4\n", explanation="other")


def repro_result(passed: bool, message: str = "assert -1 == 3", symbol: str | None = "test_repro"):
    fails = [] if passed else [
        Failure(kind="test", file=TEST_PATH, line=5, symbol=symbol, message=message)
    ]
    return CheckResult(stage="tests", passed=passed, failures=fails, failing_tests=len(fails))


def repro_rules(calc: str, test: str) -> CheckResult:
    """The generated test fails on the buggy code and passes on the fixed one."""
    return repro_result(calc == "ok")


def test_a_test_that_fails_on_the_original_drives_a_normal_reliability_fix(tmp_path):
    h = Harness(
        tmp_path,
        {"bug": checks(0), "ok": checks(0)},
        issue="add() is wrong",
        answers=[GOOD_TEST, "ok"],
        test_file=repro_rules,
    )
    result = h.run()
    assert (result.status, result.reliability, result.stop_reason) == ("fixed", "normal", "success")
    prompt = h.llm.calls[1][1]["content"]  # what the Programmer saw
    assert f"### FILE {TEST_PATH} (full)" in prompt and "assert add(1, 2) == 3" in prompt
    assert f"[test] {TEST_PATH}:5 test_repro: assert -1 == 3" in prompt
    assert TEST_PATH not in result.diff  # the generated test is not part of the fix
    # checked on the original, then after the fix; the file never stays in the workspace
    assert [path for path, _ in h.seen_tests] == [TEST_PATH, TEST_PATH]


def test_the_tester_does_not_see_a_fix_and_gets_the_original_code(tmp_path):
    h = Harness(
        tmp_path,
        {"bug": checks(0), "ok": checks(0)},
        issue="add() is wrong",
        answers=[GOOD_TEST, "ok"],
        test_file=repro_rules,
    )
    h.run()
    system, user = h.llm.calls[0]
    assert "pkg/calc.py (full)\nbug\n" in user["content"]
    assert f"saved as `{TEST_PATH}`" in system["content"]
    assert "FAIL on the current code" in system["content"]


def test_a_test_that_passes_on_the_original_is_rewritten(tmp_path):
    def rules(calc, test):
        return repro_result(calc == "ok" or "add(1, 2)" not in test)

    h = Harness(
        tmp_path,
        {"bug": checks(0), "ok": checks(0)},
        issue="add() is wrong",
        answers=[OTHER_TEST, GOOD_TEST, "ok"],
        test_file=rules,
    )
    result = h.run()
    assert (result.status, result.reliability) == ("fixed", "normal")
    retry = h.llm.calls[1][1]["content"]
    assert "does not reproduce the bug" in retry and "assert 3 == 4" in retry


def test_a_broken_test_is_not_a_bug_and_is_rewritten(tmp_path):
    broken = repro_result(False, "ModuleNotFoundError: No module named 'pkg.nope'")
    results = iter([broken, repro_result(False), repro_result(True)])
    h = Harness(
        tmp_path,
        {"bug": checks(0), "ok": checks(0)},
        issue="add() is wrong",
        answers=[OTHER_TEST, GOOD_TEST, "ok"],
        test_file=lambda calc, test: next(results),
    )
    result = h.run()
    assert result.status == "fixed"
    retry = h.llm.calls[1][1]["content"]
    assert "not the bug" in retry and "No module named 'pkg.nope'" in retry
    assert len(h.llm.calls) == 3  # the broken test never reached the Programmer


def test_without_a_reproducing_test_the_run_goes_on_as_less_reliable(tmp_path):
    h = Harness(
        tmp_path,
        {"bug": checks(0), "ok": checks(0)},
        Config(max_test_attempts=3),
        issue="add() is wrong",
        answers=[GOOD_TEST, GOOD_TEST, GOOD_TEST, "ok"],
        test_file=lambda calc, test: repro_result(True),
    )
    result = h.run()
    assert (result.status, result.reliability) == ("fixed", "reduced")
    assert len(h.seen_tests) == 3  # exactly max_test_attempts tries


def test_unusable_tester_answers_spend_attempts_and_the_run_goes_on(tmp_path):
    garbage = LiteLLMClient(LlmConfig(), None, ScriptedCompletion(["not json"] * 6))
    h = Harness(
        tmp_path,
        {"bug": checks(0)},
        Config(max_test_attempts=2, max_attempts=1),
        issue="add() is wrong",
        llm=garbage,
        test_file=repro_rules,
    )
    result = h.run()
    assert (result.status, result.reliability) == ("not_fixed", "reduced")
    assert h.seen_tests == []


def test_the_programmer_cannot_edit_the_generated_test(tmp_path):
    attack = Patch(files={TEST_PATH: "def test_repro():\n    pass\n"}, explanation="weaken it")
    h = Harness(
        tmp_path,
        {"bug": checks(0), "ok": checks(0)},
        issue="add() is wrong",
        answers=[GOOD_TEST, attack, "ok"],
        test_file=repro_rules,
    )
    result = h.run()
    assert (result.status, result.best_attempt) == ("fixed", 1)  # the refused patch spent attempt 0
    assert all(test == GOOD_TEST.content for _, test in h.seen_tests)


def test_basic_tests_for_a_project_without_tests(tmp_path):
    h = Harness(
        tmp_path,
        {"bug": checks(0), "ok": checks(0)},
        answers=[GOOD_TEST, "ok"],
        test_file=repro_rules,
        with_tests=False,
    )
    result = h.run()
    assert (result.status, result.reliability) == ("fixed", "reduced")
    assert "basic tests" in h.llm.calls[0][0]["content"]


def test_basic_tests_that_pass_mean_no_bugs_found_but_less_reliably(tmp_path):
    h = Harness(
        tmp_path,
        {"bug": checks(0)},
        answers=[GOOD_TEST],
        test_file=lambda calc, test: repro_result(True),
        with_tests=False,
    )
    result = h.run()
    assert (result.status, result.reliability) == ("no_bugs_found", "reduced")
    assert len(h.llm.calls) == 1  # the Programmer was never asked


def test_the_tester_is_not_asked_when_the_original_checks_fail(tmp_path):
    h = Harness(
        tmp_path,
        {"bug": checks(2), "ok": checks(0)},
        issue="add() is wrong",
        answers=["ok"],
        test_file=repro_rules,
    )
    result = h.run()
    assert (result.status, result.reliability) == ("fixed", "reduced")
    assert h.seen_tests == [] and len(h.llm.calls) == 1


def test_the_tester_is_not_asked_when_the_project_has_tests_and_no_issue(tmp_path):
    h = Harness(tmp_path, {"bug": checks(0)})
    assert h.run().status == "no_bugs_found" and h.llm.calls == []
