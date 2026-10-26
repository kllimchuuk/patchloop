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
