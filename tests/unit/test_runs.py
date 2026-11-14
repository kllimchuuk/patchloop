"""Run records on disk (decision 29): saved by `fix`, read by `apply`."""

import json
from datetime import datetime

import pytest

from patchloop import runs
from patchloop.runs import RunRecord, RunRecordError, load_record, new_run_id, save_record
from patchloop.schemas import SCHEMA_VERSION, RunResult

NOW = datetime(2026, 11, 14, 15, 30, 42)


def record(run_id="20261114-153042-a3f9", **result):
    return RunRecord(
        run_id=run_id,
        project="/work/proj",
        issue="add() is wrong",
        result=RunResult(status="fixed", diff="--- a/x\n+++ b/x\n", **result),
    )


def test_run_id_has_the_documented_shape():
    run_id = new_run_id(NOW)
    assert run_id.startswith("20261114-153042-")
    assert runs.RUN_ID.fullmatch(run_id)


def test_two_ids_in_the_same_second_differ(monkeypatch):
    suffixes = iter(["a3f9", "0b1c"])
    monkeypatch.setattr(runs.secrets, "token_hex", lambda n: next(suffixes))
    assert new_run_id(NOW) != new_run_id(NOW)


def test_save_then_load_round_trips(tmp_path):
    saved = record()
    save_record(tmp_path, saved)
    assert (tmp_path / saved.run_id / "record.json").is_file()
    assert load_record(tmp_path, saved.run_id) == saved


def test_runs_dir_is_created_and_tilde_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    save_record(runs.Path("~/.patchloop/runs"), record())
    assert (tmp_path / ".patchloop/runs/20261114-153042-a3f9/record.json").is_file()


@pytest.mark.parametrize(
    "bad", ["../x", "..", "a/b", "/etc/passwd", "", "20261114-153042", "20261114-153042-ABCD"]
)
def test_a_bad_run_id_is_rejected_before_touching_the_disk(tmp_path, bad):
    with pytest.raises(RunRecordError, match="run id"):
        load_record(tmp_path, bad)
    with pytest.raises(RunRecordError, match="run id"):
        save_record(tmp_path, record(run_id=bad))
    assert list(tmp_path.iterdir()) == []


def test_an_unknown_run_is_a_clear_error(tmp_path):
    with pytest.raises(RunRecordError, match="no run 20261114-153042-a3f9"):
        load_record(tmp_path, "20261114-153042-a3f9")


def test_a_corrupt_record_is_a_clear_error(tmp_path):
    folder = tmp_path / "20261114-153042-a3f9"
    folder.mkdir()
    (folder / "record.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(RunRecordError, match="unreadable"):
        load_record(tmp_path, "20261114-153042-a3f9")


def test_a_record_of_another_schema_version_is_refused(tmp_path):
    saved = record()
    save_record(tmp_path, saved)
    path = tmp_path / saved.run_id / "record.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = SCHEMA_VERSION - 1
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RunRecordError, match="schema version"):
        load_record(tmp_path, saved.run_id)


def test_saving_never_overwrites_an_existing_run(tmp_path):
    save_record(tmp_path, record())
    with pytest.raises(RunRecordError, match="already exists"):
        save_record(tmp_path, record())


def test_no_temp_file_is_left_behind(tmp_path):
    save_record(tmp_path, record())
    assert [p.name for p in (tmp_path / "20261114-153042-a3f9").iterdir()] == ["record.json"]
