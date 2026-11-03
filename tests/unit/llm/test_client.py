import pytest
from support.fake_completion import ScriptedCompletion

from patchloop.config import LlmConfig
from patchloop.llm.cache import AnswerCache
from patchloop.llm.client import FakeLLMClient, LiteLLMClient, LLMError
from patchloop.schemas import Patch

MESSAGES = [{"role": "user", "content": "fix it"}]
VALID = '{"files": {"a.py": "x = 1\\n"}, "explanation": "fixed"}'


def _client(items, cache=None, config=None):
    completion = ScriptedCompletion(items)
    return LiteLLMClient(config or LlmConfig(), cache, completion), completion.calls


def test_valid_answer_is_parsed_and_schema_is_sent():
    client, calls = _client([VALID])
    patch = client.complete(MESSAGES, Patch)
    assert patch.files == {"a.py": "x = 1\n"}
    assert calls[0]["response_format"]["json_schema"]["schema"]["title"] == "Patch"


def test_context_window_is_passed_to_the_model():
    client, calls = _client([VALID])
    client.complete(MESSAGES, Patch)
    assert calls[0]["num_ctx"] == LlmConfig().num_ctx


@pytest.mark.parametrize(("thinking", "effort"), [(False, "none"), (True, "low")])
def test_thinking_maps_to_reasoning_effort(thinking, effort):
    client, calls = _client([VALID], config=LlmConfig(thinking=thinking))
    client.complete(MESSAGES, Patch)
    assert calls[0]["reasoning_effort"] == effort


def test_thinking_is_off_by_default():
    assert LlmConfig().thinking is False


def test_invalid_answer_is_retried_once_with_the_error():
    client, calls = _client(['{"files": 1}', VALID])
    assert client.complete(MESSAGES, Patch).explanation == "fixed"
    retry = calls[1]["messages"]
    assert retry[-1]["role"] == "user" and "invalid" in retry[-1]["content"]


def test_two_invalid_answers_raise():
    client, calls = _client(["not json", "still not json"])
    with pytest.raises(LLMError):
        client.complete(MESSAGES, Patch)
    assert len(calls) == 2


def test_unreachable_model_is_a_clear_error():
    client, _ = _client([ConnectionError("refused")])
    with pytest.raises(LLMError, match="cannot get an answer"):
        client.complete(MESSAGES, Patch)


def test_cache_avoids_the_second_call(tmp_path):
    client, calls = _client([VALID], AnswerCache(tmp_path))
    first = client.complete(MESSAGES, Patch)
    second = client.complete(MESSAGES, Patch)
    assert first == second and len(calls) == 1


def test_fake_client_returns_prepared_answers_in_order():
    fake = FakeLLMClient(
        [
            Patch(files={"a.py": ""}, explanation="one"),
            {"files": {"a.py": ""}, "explanation": "two"},
        ]
    )
    assert fake.complete(MESSAGES, Patch).explanation == "one"
    assert fake.complete(MESSAGES, Patch).explanation == "two"
    with pytest.raises(LLMError):
        fake.complete(MESSAGES, Patch)
