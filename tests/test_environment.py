import subprocess
import urllib.error

from patchloop.config import Config
from patchloop.environment import check_docker, check_ollama, check_python


def _done(code, out=""):
    return lambda cmd: subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")


def test_python_version():
    assert check_python((3, 11, 9)).ok
    assert not check_python((3, 10, 0)).ok


def test_docker_ok_and_down():
    assert check_docker(_done(0, "28.5.1\n")).detail == "28.5.1"
    assert not check_docker(_done(1)).ok


def test_docker_missing_binary_is_a_fail_not_a_crash():
    def run(cmd):
        raise FileNotFoundError("docker")

    assert not check_docker(run).ok


def test_ollama_unreachable_is_a_fail():
    def get(url):
        raise urllib.error.URLError("refused")

    items = check_ollama(Config(), get)
    assert [i.ok for i in items] == [False]
    assert "ollama.com" in items[0].hint


def test_ollama_model_present_and_missing():
    present = check_ollama(
        Config(), lambda url: {"models": [{"name": "qwen3.5:9b-q4_K_M"}]}
    )
    assert all(i.ok for i in present)
    missing = check_ollama(Config(), lambda url: {"models": [{"name": "other:1b"}]})
    assert missing[1].ok is False and missing[1].hint == "ollama pull qwen3.5:9b-q4_K_M"
