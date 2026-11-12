import os

import pytest
from support.fake_completion import ScriptedCompletion
from support.projects import make_buggy_project, write_files

from patchloop.agents.tester import MAX_PATH_VARIANTS, PreviousTry, free_path, propose_test
from patchloop.config import LlmConfig, LoopConfig
from patchloop.llm.client import FakeLLMClient, LiteLLMClient
from patchloop.schemas import TestPlan

LOOP = LoopConfig()
PATH = "tests/test_patchloop_generated.py"
PLAN = TestPlan(content="def test_x():\n    assert 1\n", explanation="x")


@pytest.fixture
def project(tmp_path):
    return make_buggy_project(tmp_path)


def _prompt(project, **kwargs):
    """The (system, user) messages that `propose_test` sends to the model."""
    llm = FakeLLMClient([PLAN])
    kwargs = {"mode": "issue", "path": PATH, "framework": "pytest"} | kwargs
    propose_test(llm, project, LOOP, **kwargs)
    system, user = llm.calls[0]
    return system["content"], user["content"]


def test_a_valid_answer_is_returned_as_the_plan(project):
    result = propose_test(
        FakeLLMClient([PLAN]), project, LOOP, mode="issue", path=PATH, framework="pytest"
    )
    assert result.plan == PLAN and result.error is None


def test_the_prompt_has_the_issue_the_code_the_path_and_the_framework(project):
    system, user = _prompt(project, issue="add() subtracts", language="sk")
    assert "## Bug description\nadd() subtracts" in user
    assert "### FILE pkg/calc.py (full)\ndef add(a, b):\n    return a - b" in user
    assert f"saved as `{PATH}`" in system and "Test framework: pytest" in system
    assert "in this language: sk" in system
    assert "FAIL on the current code" in system


def test_basic_mode_asks_for_tests_of_key_functions_without_an_issue(tmp_path):
    system, user = _prompt(write_files(tmp_path, {"pkg/calc.py": "x = 1\n"}), mode="basic")
    assert "no tests" in system and "Bug description" not in user


def test_a_rejected_test_and_the_reason_go_back_to_the_model(project):
    previous = PreviousTry("def test_old(): ...", "It passes on the current code.")
    _, user = _prompt(project, previous=previous)
    assert "## Your previous answer was rejected" in user
    assert "It passes on the current code." in user and "def test_old(): ..." in user


def test_an_invalid_answer_is_a_spent_attempt_not_a_crash(project):
    client = LiteLLMClient(LlmConfig(), None, ScriptedCompletion(["not json", "still not"]))
    result = propose_test(client, project, LOOP, mode="issue", path=PATH, framework="pytest")
    assert result.plan is None and result.error


def test_free_path_never_picks_an_existing_file(tmp_path):
    assert free_path(tmp_path, PATH) == PATH
    write_files(tmp_path, {PATH: "", "tests/test_patchloop_generated_2.py": ""})
    assert free_path(tmp_path, PATH) == "tests/test_patchloop_generated_3.py"


def test_free_path_gives_up_instead_of_looping(tmp_path):
    names = ["tests/test_patchloop_generated.py"] + [
        f"tests/test_patchloop_generated_{n}.py" for n in range(2, MAX_PATH_VARIANTS + 1)
    ]
    write_files(tmp_path, dict.fromkeys(names, ""))
    assert free_path(tmp_path, PATH) is None


def test_free_path_gives_up_when_the_tests_directory_is_a_link(tmp_path):
    (tmp_path / "elsewhere").mkdir()
    os.symlink(tmp_path / "elsewhere", tmp_path / "tests")
    assert free_path(tmp_path, PATH) is None


def test_an_answer_that_was_not_a_test_is_described_without_a_previous_test(project):
    _, user = _prompt(project, previous=PreviousTry("", "It was not a valid test file: x"))
    assert "## Your previous answer was rejected\nProblem: It was not a valid test file: x" in user
    assert "PREVIOUS TEST" not in user
