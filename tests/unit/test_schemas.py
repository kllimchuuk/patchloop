import pytest
from pydantic import ValidationError

from patchloop.schemas import SCHEMA_VERSION, Failure, Patch, RunResult


def test_round_trip():
    result = RunResult(
        status="fixed", best_attempt=1, diff="--- a\n+++ b\n", stop_reason="success"
    )
    assert RunResult.model_validate_json(result.model_dump_json()) == result
    assert result.schema_version == SCHEMA_VERSION


def test_extra_field_is_forbidden():
    with pytest.raises(ValidationError):
        Patch(files={"a.py": "x = 1\n"}, explanation="e", surprise=1)


def test_invalid_status_is_rejected():
    with pytest.raises(ValidationError):
        RunResult(status="done")


def test_models_are_frozen():
    failure = Failure(kind="test", message="boom")
    with pytest.raises(ValidationError):
        failure.message = "other"


def test_line_numbers_start_at_one():
    with pytest.raises(ValidationError):
        Failure(kind="build", message="m", line=0)


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../x.py",
        "a/../../x.py",
        "./a.py",
        ".git/config",
        "a/.git/hooks/x",
        "",
        "a\\b.py",
        "a\0.py",
    ],
)
def test_patch_rejects_unsafe_paths(path):
    with pytest.raises(ValidationError):
        Patch(files={path: "x"}, explanation="e")


def test_patch_rejects_empty_files():
    with pytest.raises(ValidationError):
        Patch(files={}, explanation="e")


def test_patch_accepts_nested_relative_path():
    patch = Patch(files={"src/pkg/a.py": "x = 1\n"}, explanation="e")
    assert list(patch.files) == ["src/pkg/a.py"]
