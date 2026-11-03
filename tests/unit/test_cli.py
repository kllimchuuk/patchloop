from typer.testing import CliRunner

from patchloop import __version__
from patchloop.cli import app
from patchloop.environment import CheckItem

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0 and __version__ in result.output


def test_check_exits_zero_when_every_check_passes(monkeypatch):
    monkeypatch.setattr("patchloop.cli.run_checks", lambda cfg: [CheckItem("A", True, "fine")])
    assert runner.invoke(app, ["check"]).exit_code == 0


def test_check_exits_one_and_shows_the_hint_when_a_check_fails(monkeypatch):
    items = [CheckItem("B", False, "down", "start it")]
    monkeypatch.setattr("patchloop.cli.run_checks", lambda cfg: items)
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 1 and "start it" in result.output
