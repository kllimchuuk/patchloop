import pytest
from support.fake_completion import ScriptedCompletion
from support.projects import make_buggy_project, write_files

from patchloop.agents.programmer import HistoryEntry, propose_patch
from patchloop.config import LlmConfig, LoopConfig
from patchloop.llm.client import FakeLLMClient, LiteLLMClient, LLMError, LLMInvalidAnswer
from patchloop.schemas import Failure, Patch

LOOP = LoopConfig()
FAILURE = Failure(
    kind="test", file="tests/test_calc.py", line=4, symbol="test_add", message="assert -1 == 3"
)
FIX = Patch(files={"pkg/calc.py": "def add(a, b):\n    return a + b\n"}, explanation="plus")


@pytest.fixture
def project(tmp_path):
    return make_buggy_project(tmp_path)


def _real_client(items):
    return LiteLLMClient(LlmConfig(), None, ScriptedCompletion(items))


def _prompt(project, failures=(FAILURE,), **kwargs):
    """The (system, user) messages that `propose_patch` sends to the model."""
    llm = FakeLLMClient([FIX])
    propose_patch(llm, project, list(failures), LOOP, **kwargs)
    system, user = llm.calls[0]
    return system["content"], user["content"]


def test_a_valid_answer_is_returned_as_the_patch(project):
    result = propose_patch(FakeLLMClient([FIX]), project, [FAILURE], LOOP)
    assert result.patch == FIX and result.error is None


def test_system_prompt_names_the_explanation_language(project):
    system, _ = _prompt(project, language="sk")
    assert "in this language: sk" in system


def test_prompt_lists_the_failure_and_the_bug_description(project):
    _, user = _prompt(project, issue="add() subtracts")
    assert "## Bug description\nadd() subtracts" in user
    assert "- [test] tests/test_calc.py:4 test_add: assert -1 == 3" in user


def test_prompt_shows_source_files_before_tests(project):
    _, user = _prompt(project)
    assert "### FILE pkg/calc.py (full)\ndef add(a, b):\n    return a - b" in user
    assert user.index("pkg/calc.py (full)") < user.index("tests/test_calc.py (full)")


def test_prompt_includes_earlier_attempts_and_reviewer_comments(project):
    earlier = HistoryEntry(
        "changed the sign",
        [Failure(kind="test", file="pkg/calc.py", line=2, message="still wrong")],
    )
    _, user = _prompt(project, history=[earlier], review_comments=["add a docstring"])
    assert "Attempt 1: changed the sign" in user and "still wrong" in user
    assert "- add a docstring" in user


def test_raw_tail_is_shown_when_the_parser_found_nothing(project):
    failure = Failure(kind="build", message="build failed", raw_tail="line a\nline b")
    _, user = _prompt(project, failures=[failure])
    assert "    line a\n    line b" in user


def test_many_failures_are_cut_with_a_count(project):
    many = [Failure(kind="lint", file="pkg/calc.py", line=1, message=f"m{i}") for i in range(14)]
    _, user = _prompt(project, failures=many)
    assert "m9" in user and "m10" not in user
    assert "... and 4 more" in user


def test_new_files_are_allowed(project):
    new = Patch(files={"pkg/extra.py": "X = 1\n"}, explanation="e")
    assert propose_patch(FakeLLMClient([new]), project, [FAILURE], LOOP).patch == new


def test_rewriting_a_file_that_was_not_shown_is_refused(project):
    write_files(project, {"other.py": "keep = 1\n"})
    patch = Patch(files={"other.py": "keep = 2\n"}, explanation="e")
    result = propose_patch(FakeLLMClient([patch]), project, [FAILURE], LOOP)
    assert result.patch is None
    assert result.error == "the patch rewrites other.py, which was not shown in full"


def test_rewriting_an_excerpt_only_file_is_refused(project):
    write_files(project, {"pkg/calc.py": "x = 1\n" * 5000})
    patch = Patch(files={"pkg/calc.py": "x = 2\n"}, explanation="e")
    llm = FakeLLMClient([patch])
    result = propose_patch(llm, project, [FAILURE], LOOP)
    assert result.patch is None and "not shown in full" in result.error
    assert "### FILE pkg/calc.py (excerpt)" in llm.calls[0][1]["content"]


def test_a_patch_that_changes_nothing_is_an_error(project):
    same = Patch(files={"pkg/calc.py": "def add(a, b):\n    return a - b\n"}, explanation="e")
    result = propose_patch(FakeLLMClient([same]), project, [FAILURE], LOOP)
    assert result.patch is None and result.error == "the patch changes nothing"


def test_two_invalid_answers_spend_the_attempt_without_crashing(project):
    llm = _real_client(["not json", '{"files": {}, "explanation": "x"}'])
    result = propose_patch(llm, project, [FAILURE], LOOP)
    assert result.patch is None and "invalid answer twice" in result.error


def test_an_unreachable_model_is_not_swallowed(project):
    llm = _real_client([ConnectionError("down")])
    with pytest.raises(LLMError) as info:
        propose_patch(llm, project, [FAILURE], LOOP)
    assert not isinstance(info.value, LLMInvalidAnswer)


def test_an_unsafe_path_from_the_model_counts_as_an_invalid_answer(project):
    bad = '{"files": {"../evil.py": "x"}, "explanation": "x"}'
    result = propose_patch(_real_client([bad, bad]), project, [FAILURE], LOOP)
    assert result.patch is None
    assert "invalid answer twice" in result.error and "../evil.py" in result.error


GEN_TEST = "tests/test_calc.py"


def test_a_read_only_file_is_labelled_and_the_system_prompt_says_so(project):
    llm = FakeLLMClient([FIX])
    propose_patch(llm, project, [FAILURE], LOOP, protected=[GEN_TEST])
    system, user = (m["content"] for m in llm.calls[0])
    assert f"### FILE {GEN_TEST} (read-only)" in user
    assert "### FILE pkg/calc.py (full)" in user
    assert '"read-only" must not be changed' in system


def test_a_changed_read_only_file_is_refused(project):
    weaker = Patch(files={GEN_TEST: "def test_add():\n    pass\n"}, explanation="e")
    result = propose_patch(FakeLLMClient([weaker]), project, [FAILURE], LOOP, protected=[GEN_TEST])
    assert result.patch is None and "must not be edited" in result.error


def test_an_unchanged_copy_of_a_read_only_file_is_dropped_from_the_patch(project):
    echoed = Patch(
        files={"pkg/calc.py": FIX.files["pkg/calc.py"], GEN_TEST: (project / GEN_TEST).read_text()},
        explanation="fix + echo",
    )
    result = propose_patch(FakeLLMClient([echoed]), project, [FAILURE], LOOP, protected=[GEN_TEST])
    assert result.error is None and result.patch.files == FIX.files


def test_a_patch_with_only_an_echo_of_a_read_only_file_changes_nothing(project):
    echo = Patch(files={GEN_TEST: (project / GEN_TEST).read_text()}, explanation="e")
    result = propose_patch(FakeLLMClient([echo]), project, [FAILURE], LOOP, protected=[GEN_TEST])
    assert result.patch is None and result.error == "the patch changes nothing"


def test_a_refused_attempt_is_shown_with_its_reason_and_without_errors_left(project):
    refused = HistoryEntry("the patch changes tests/x.py, a generated test", [], refused=True)
    _, user = _prompt(project, history=[refused])
    assert "Attempt 1 was refused and not applied: the patch changes tests/x.py" in user
    assert "Errors after it" not in user
