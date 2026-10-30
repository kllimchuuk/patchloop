import pytest

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
    (tmp_path / "pkg").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    source = "def add(a, b):\n    return a - b\n"
    (tmp_path / "pkg" / "calc.py").write_text(source, encoding="utf-8")
    (tmp_path / "tests" / "test_calc.py").write_text(
        "from pkg.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    return tmp_path


def test_prompt_contains_failures_code_issue_history_and_comments(project):
    llm = FakeLLMClient([FIX])
    history = [
        HistoryEntry(
            "changed the sign",
            (Failure(kind="test", file="pkg/calc.py", line=2, message="still wrong"),),
        )
    ]
    result = propose_patch(
        llm,
        project,
        [FAILURE],
        LOOP,
        issue="add() subtracts",
        history=history,
        review_comments=["add a docstring"],
        language="sk",
    )
    assert result.patch == FIX and result.error is None
    system, user = llm.calls[0]
    assert system["role"] == "system" and "in this language: sk" in system["content"]
    text = user["content"]
    assert "## Bug description\nadd() subtracts" in text
    assert "- [test] tests/test_calc.py:4 test_add: assert -1 == 3" in text
    assert "### FILE pkg/calc.py (full)\ndef add(a, b):\n    return a - b" in text
    assert "### FILE tests/test_calc.py (full)" in text
    assert text.index("pkg/calc.py (full)") < text.index("tests/test_calc.py (full)")
    assert "Attempt 1: changed the sign" in text and "still wrong" in text
    assert "- add a docstring" in text


def test_raw_tail_is_shown_when_the_parser_found_nothing(project):
    llm = FakeLLMClient([FIX])
    failure = Failure(kind="build", message="build failed", raw_tail="line a\nline b")
    propose_patch(llm, project, [failure], LOOP)
    assert "    line a\n    line b" in llm.calls[0][1]["content"]


def test_many_failures_are_cut_with_a_count(project):
    llm = FakeLLMClient([FIX])
    many = [Failure(kind="lint", file="pkg/calc.py", line=1, message=f"m{i}") for i in range(14)]
    propose_patch(llm, project, many, LOOP)
    text = llm.calls[0][1]["content"]
    assert "m9" in text and "m10" not in text and "... and 4 more" in text


def test_new_files_are_allowed(project):
    new = Patch(files={"pkg/extra.py": "X = 1\n"}, explanation="e")
    assert propose_patch(FakeLLMClient([new]), project, [FAILURE], LOOP).patch == new


def test_rewriting_a_file_that_was_not_shown_is_refused(project):
    (project / "other.py").write_text("keep = 1\n", encoding="utf-8")
    patch = Patch(files={"other.py": "keep = 2\n"}, explanation="e")
    result = propose_patch(FakeLLMClient([patch]), project, [FAILURE], LOOP)
    assert result.patch is None and "not shown in full" in result.error


def test_rewriting_an_excerpt_only_file_is_refused(project):
    (project / "pkg" / "calc.py").write_text("x = 1\n" * 5000, encoding="utf-8")
    patch = Patch(files={"pkg/calc.py": "x = 2\n"}, explanation="e")
    llm = FakeLLMClient([patch])
    result = propose_patch(llm, project, [FAILURE], LOOP)
    assert result.patch is None and "not shown in full" in result.error
    assert "### FILE pkg/calc.py (excerpt)" in llm.calls[0][1]["content"]


def test_a_patch_that_changes_nothing_is_an_error(project):
    same = Patch(files={"pkg/calc.py": "def add(a, b):\n    return a - b\n"}, explanation="e")
    result = propose_patch(FakeLLMClient([same]), project, [FAILURE], LOOP)
    assert result.patch is None and result.error == "the patch changes nothing"


def _real_client(answers):
    items = list(answers)

    def completion(**kwargs):
        item = items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return LiteLLMClient(LlmConfig(), None, completion)


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
    assert result.patch is None and result.error
