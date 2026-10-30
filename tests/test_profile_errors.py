from pathlib import Path

import pytest

from patchloop.profiles import PythonProfile
from patchloop.profiles.python_errors import parse_check, relative_path
from patchloop.sandbox.runner import ExecResult

OUTPUTS = Path(__file__).parent / "fixtures" / "outputs"


def _run(stage, name, exit_code=1, **extra):
    text = (OUTPUTS / name).read_text(encoding="utf-8")
    result = ExecResult(exit_code=exit_code, stdout=text, stderr="", duration_s=0.5, **extra)
    return parse_check(stage, result, tail_lines=10)


def test_compileall_syntax_errors():
    check = _run("build", "compile.txt")
    assert not check.passed
    assert [(f.file, f.line) for f in check.failures] == [("bad.py", 1), ("t/test_syn.py", 1)]
    assert {f.kind for f in check.failures} == {"build"}
    assert {f.message for f in check.failures} == {"SyntaxError: invalid syntax"}
    assert check.failing_tests == 0


def test_ruff_concise_lines():
    check = _run("lint", "ruff.txt")
    assert [(f.file, f.line, f.symbol) for f in check.failures] == [
        ("pkg/calc.py", 1, "I001"),
        ("pkg/calc.py", 1, "F401"),
        ("tests/test_calc.py", 1, "I001"),
    ]
    assert check.failures[1].message == "F401 `os` imported but unused"
    assert all(f.kind == "lint" for f in check.failures)


def test_pytest_assertion_failure():
    check = _run("tests", "pytest_fail.txt")
    (failure,) = check.failures
    assert (failure.kind, failure.file, failure.line) == ("test", "tests/test_calc.py", 4)
    assert failure.symbol == "test_add"
    assert failure.message == "assert -1 == 3"
    assert check.failing_tests == 1


def test_pytest_several_failures_and_exception_type():
    check = _run("tests", "pytest_fail_all.txt")
    assert [(f.symbol, f.line) for f in check.failures] == [("test_add", 4), ("test_boom", 10)]
    assert check.failures[1].message == "ValueError: boom"
    assert check.failing_tests == 2  # the passed test is not counted


def test_pytest_import_error_points_at_the_test_module():
    check = _run("tests", "pytest_import.txt")
    (failure,) = check.failures
    assert (failure.file, failure.line, failure.symbol) == ("t/test_imp.py", 1, None)
    assert failure.kind == "test"
    assert check.failing_tests == 1  # counted once, not once more from the "Interrupted" banner


def test_pytest_collection_syntax_error_uses_the_module_file():
    check = _run("tests", "pytest_syntax.txt")
    (failure,) = check.failures
    assert (failure.file, failure.line) == ("t/test_syn.py", 1)


def test_passing_check_has_no_failures():
    result = ExecResult(exit_code=0, stdout="3 passed in 0.01s", stderr="", duration_s=1.0)
    check = parse_check("tests", result, tail_lines=10)
    assert check.passed and check.failures == [] and check.failing_tests == 0


def test_pytest_collecting_nothing_is_not_a_failure():
    result = ExecResult(exit_code=5, stdout="no tests ran in 0.01s", stderr="", duration_s=1.0)
    assert parse_check("tests", result, tail_lines=10).passed
    assert not parse_check("build", result, tail_lines=10).passed


@pytest.mark.parametrize("stage", ["build", "lint", "tests"])
def test_unparsable_failure_keeps_the_raw_tail(stage):
    out = "\n".join(f"line {i}" for i in range(50))
    result = ExecResult(exit_code=2, stdout=out, stderr="boom", duration_s=1.0)
    check = parse_check(stage, result, tail_lines=5)
    (failure,) = check.failures
    assert failure.raw_tail.splitlines() == ["line 46", "line 47", "line 48", "line 49", "boom"]
    assert "exit code 2" in failure.message
    assert check.failing_tests == (1 if stage == "tests" else 0)


def test_failed_check_with_no_output_still_has_a_failure():
    result = ExecResult(exit_code=1, stdout="", stderr="", duration_s=1.0)
    assert len(parse_check("lint", result, tail_lines=5).failures) == 1


def test_timeout_and_oom_are_runtime_failures():
    slow = ExecResult(exit_code=124, stdout="partial", stderr="", duration_s=9.0, timed_out=True)
    check = parse_check("tests", slow, tail_lines=5)
    assert (check.failures[0].kind, check.failures[0].message) == ("runtime", "tests timed out")
    assert check.failures[0].raw_tail == "partial" and not check.passed
    oom = ExecResult(exit_code=137, stdout="", stderr="", duration_s=1.0, oom_killed=True)
    assert "out of memory" in parse_check("build", oom, tail_lines=5).failures[0].message


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/work/pkg/a.py", "pkg/a.py"),
        ("./pkg/a.py", "pkg/a.py"),
        ("pkg/../pkg/a.py", "pkg/a.py"),
        ("/usr/local/lib/python3.12/site.py", None),
        ("/etc/passwd", None),
        ("../outside.py", None),
        ("/work/../etc/passwd", None),
        ("", None),
    ],
)
def test_relative_path_drops_everything_outside_the_workspace(raw, expected):
    assert relative_path(raw) == expected


def test_profile_delegates_to_the_parser():
    result = ExecResult(exit_code=1, stdout="a.py:3:1: F401 x", stderr="", duration_s=1.0)
    check = PythonProfile().parse_check("lint", result, 5)
    assert check.failures[0].file == "a.py"
