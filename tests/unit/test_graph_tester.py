"""The Tester inside the repair loop (SPEC §3 step 4, §9)."""

import os
import shutil

from support.fake_completion import ScriptedCompletion
from test_graph import SOURCE, Harness, checks

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
    assert f"### FILE {TEST_PATH} (read-only)" in prompt and "assert add(1, 2) == 3" in prompt
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


def test_a_refused_patch_and_its_reason_reach_the_next_prompt(tmp_path):
    weaker = "def test_repro():\n    pass\n"
    echo = Patch(files={"pkg/calc.py": "v1", TEST_PATH: weaker}, explanation="e")
    h = Harness(
        tmp_path,
        {"bug": checks(0), "ok": checks(0)},
        issue="add() is wrong",
        answers=[GOOD_TEST, echo, "ok"],
        test_file=repro_rules,
    )
    assert h.run().status == "fixed"
    second = h.llm.calls[2][1]["content"]
    assert "Attempt 1 was refused and not applied" in second and "must not be edited" in second
    assert second != h.llm.calls[1][1]["content"]  # not the same prompt again


def test_an_unchanged_copy_of_the_generated_test_does_not_spoil_a_good_fix(tmp_path):
    echo = Patch(files={"pkg/calc.py": "ok", TEST_PATH: GOOD_TEST.content}, explanation="fix")
    h = Harness(
        tmp_path,
        {"bug": checks(0), "ok": checks(0)},
        issue="add() is wrong",
        answers=[GOOD_TEST, echo],
        test_file=repro_rules,
    )
    result = h.run()
    assert (result.status, result.best_attempt) == ("fixed", 0)
    assert TEST_PATH not in result.diff


def test_an_unusable_tester_answer_is_explained_to_the_model_on_the_next_try(tmp_path):
    fix = Patch(files={"pkg/calc.py": "ok"}, explanation="fix").model_dump_json()
    script = ScriptedCompletion(["not json", "not json", GOOD_TEST.model_dump_json(), fix])
    h = Harness(
        tmp_path,
        {"bug": checks(0), "ok": checks(0)},
        issue="add() is wrong",
        llm=LiteLLMClient(LlmConfig(), None, script),
        test_file=repro_rules,
    )
    assert h.run().status == "fixed"
    first, third = script.calls[0], script.calls[2]  # the first try, then the second one
    assert "previous answer was rejected" not in first["messages"][1]["content"]
    retry = third["messages"][1]["content"]
    assert "previous answer was rejected" in retry and "not a valid test file" in retry


def test_the_tester_gives_up_quietly_when_tests_is_a_link(tmp_path):
    fix = Patch(files={SOURCE: "ok"}, explanation="fix")
    h = Harness(
        tmp_path,
        {"bug": checks(0), "ok": checks(0)},
        issue="add() is wrong",
        answers=[fix],
        test_file=repro_rules,
        with_tests=False,
    )
    (h.project / "elsewhere").mkdir()
    os.symlink(h.project / "elsewhere", h.project / "tests")
    result = h.engine.run(h.issue)  # no hang, no crash, and the Tester is not even asked
    assert result.reliability == "reduced" and h.seen_tests == [] and len(h.llm.calls) == 1


def test_no_bugs_found_says_why(tmp_path):
    passes = Harness(
        tmp_path / "a",
        {"bug": checks(0)},
        answers=[GOOD_TEST],
        test_file=lambda calc, test: repro_result(True),
        with_tests=False,
    ).run()
    assert "Basic generated tests pass" in passes.explanation
    garbage = LiteLLMClient(LlmConfig(), None, ScriptedCompletion(["not json"] * 6))
    nothing = Harness(
        tmp_path / "b",
        {"bug": checks(0)},
        Config(max_test_attempts=2),
        llm=garbage,
        test_file=repro_rules,
        with_tests=False,
    ).run()
    assert "No usable test could be generated" in nothing.explanation
    own = Harness(tmp_path / "c", {"bug": checks(0)}).run()
    assert "project's own tests" in own.explanation


def test_cleanup_of_the_generated_test_never_follows_a_link_out_of_the_workspace(tmp_path):
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "test_patchloop_generated.py").write_text("precious\n", encoding="utf-8")
    h = Harness(
        tmp_path,
        {"bug": checks(0), "ok": checks(0)},
        issue="add() is wrong",
        answers=[GOOD_TEST, "ok"],
        test_file=repro_rules,
    )

    def hostile(docker, config, profile, setup, image, work, path):
        shutil.rmtree(work / "tests")  # code in the container replaced tests/ with a link
        os.symlink(victim, work / "tests")
        return repro_result(False)

    h.engine.test_file_fn = hostile
    h.engine.run(h.issue)
    assert (victim / "test_patchloop_generated.py").read_text() == "precious\n"
