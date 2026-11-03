import pytest

from patchloop.config import Config, ConfigError, load_config


def _load(tmp_path, text):
    path = tmp_path / "patchloop.yml"
    path.write_text(text, encoding="utf-8")
    return load_config(path)


def test_defaults_load_without_a_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_config() == Config()


def test_empty_file_gives_defaults(tmp_path):
    assert _load(tmp_path, "") == Config()


def test_file_overrides_defaults_and_untouched_keys_keep_theirs(tmp_path):
    cfg = _load(tmp_path, "max_attempts: 2\nllm:\n  model: ollama_chat/x:1b\n")
    assert cfg.max_attempts == 2
    assert cfg.llm.model == "ollama_chat/x:1b"
    assert cfg.llm.base_url == Config().llm.base_url


def test_sandbox_override(tmp_path):
    cfg = _load(tmp_path, "sandbox:\n  memory_mb: 512\n")
    assert cfg.sandbox.memory_mb == 512
    assert cfg.sandbox.cpus == Config().sandbox.cpus


def test_loop_override(tmp_path):
    cfg = _load(tmp_path, "loop:\n  tail_lines: 10\n")
    assert cfg.loop.tail_lines == 10
    assert cfg.loop.total_timeout_s == Config().loop.total_timeout_s


def test_profile_overrides_default_to_none():
    cfg = Config()
    assert (cfg.image, cfg.install, cfg.build, cfg.test, cfg.lint) == (None,) * 5
    assert cfg.env == {}


def test_profile_overrides_load_from_spec_example(tmp_path):
    cfg = _load(
        tmp_path,
        "image: python:3.12\n"
        "install: pip install -r requirements.txt\n"
        "test: pytest -x\n"
        "env:\n  DJANGO_SETTINGS_MODULE: config.settings\n  SECRET_KEY: test\n",
    )
    assert cfg.image == "python:3.12"
    assert cfg.test == "pytest -x"
    assert cfg.build is None
    assert cfg.env == {"DJANGO_SETTINGS_MODULE": "config.settings", "SECRET_KEY": "test"}


@pytest.mark.parametrize(
    "text",
    [
        "max_atempts: 2\n",  # a typo in a top-level key
        "max_attempts: 0\n",  # out of range
        "sandbox:\n  memory: 512\n",  # a typo in a section
        "loop:\n  timeout: 5\n",
        "loop:\n  tail_lines: 1\n",  # below the minimum
        "tests: x\n",  # not a profile key
        "env:\n  DEBUG: 1\n",  # env values must be strings
    ],
)
def test_invalid_config_is_an_error(tmp_path, text):
    with pytest.raises(ConfigError):
        _load(tmp_path, text)
