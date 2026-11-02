"""End-to-end smoke: real Docker sandbox and a real local model. Opt-in:
`uv run pytest -m "docker and llm" -s`. Needs Docker, a running Ollama with the configured
model, and network for the first image build. The result is reported as measured, not asserted
to be a success: a small model may fail, and the prompt is not tuned for this one example."""

import json
import time
import urllib.request

import docker
import pytest

from patchloop.config import Config
from patchloop.graph import run_fix
from patchloop.llm.client import LiteLLMClient

pytestmark = [pytest.mark.docker, pytest.mark.llm]


@pytest.fixture(scope="module")
def docker_client():
    try:
        c = docker.from_env()
        c.ping()
    except docker.errors.DockerException as exc:
        pytest.skip(f"Docker is not available: {exc}")
    return c


@pytest.fixture(scope="module")
def config():
    cfg = Config()
    try:
        with urllib.request.urlopen(f"{cfg.llm.base_url}/api/tags", timeout=5) as response:
            tags = json.load(response)
    except (OSError, ValueError) as exc:
        pytest.skip(f"Ollama is not reachable at {cfg.llm.base_url}: {exc}")
    wanted = cfg.llm.model.split("/", 1)[-1]
    if wanted not in {m["name"] for m in tags.get("models", [])}:
        pytest.skip(f"model {wanted} is not pulled in Ollama")
    return cfg


def _project(root):
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "requirements.txt").write_text("", encoding="utf-8")
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "calc.py").write_text(
        "def add(a, b):\n    return a - b\n", encoding="utf-8"
    )
    (root / "tests" / "test_calc.py").write_text(
        "from pkg.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    return root


def test_one_line_bug_with_real_model(docker_client, config, tmp_path):
    project = _project(tmp_path / "proj")
    llm = LiteLLMClient(config.llm)
    started = time.monotonic()
    result = run_fix(project, config, llm, docker_client)
    elapsed = time.monotonic() - started
    print(
        f"\nSMOKE status={result.status} stop_reason={result.stop_reason} "
        f"best_attempt={result.best_attempt} time={elapsed:.1f}s"
    )
    print(result.diff)
    # The original project is never touched, whatever the model did.
    assert (project / "pkg" / "calc.py").read_text(encoding="utf-8").endswith("a - b\n")
    assert result.status in {"fixed", "partially_fixed", "not_fixed"}
