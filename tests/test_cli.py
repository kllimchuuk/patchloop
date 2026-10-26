from typer.testing import CliRunner

from patchloop import __version__
from patchloop.cli import app
from patchloop.environment import CheckItem

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0 and __version__ in result.output


def test_check_exit_code_follows_the_checks(monkeypatch):
    monkeypatch.setattr(
        "patchloop.cli.run_checks", lambda cfg: [CheckItem("A", True, "fine")]
    )
    assert runner.invoke(app, ["check"]).exit_code == 0
    monkeypatch.setattr(
        "patchloop.cli.run_checks",
        lambda cfg: [CheckItem("B", False, "down", "start it")],
    )
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 1 and "start it" in result.output
