"""Structured LLM answers (SPEC §4, §12).

The model is forced to the JSON schema of a Pydantic class, the answer is validated, a failed
validation is retried once with the error, and a second failure raises `LLMError`. There is no
silent fallback: an unreachable model is an error with a clear message.
"""

import json
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from patchloop.config import LlmConfig
from patchloop.llm.cache import AnswerCache, cache_key

T = TypeVar("T", bound=BaseModel)
Messages = list[dict[str, str]]


class LLMError(RuntimeError):
    """The model is unreachable or did not produce a valid answer."""


class LLMClient(Protocol):
    def complete(self, messages: Messages, schema: type[T]) -> T:
        ...


def _default_completion(**kwargs: Any) -> str:
    import litellm  # imported lazily: it is slow to import and not needed in most tests

    litellm.suppress_debug_info = True
    response = litellm.completion(**kwargs)
    return response.choices[0].message.content or ""


class LiteLLMClient:
    def __init__(
        self,
        config: LlmConfig,
        cache: AnswerCache | None = None,
        completion: Callable[..., str] = _default_completion,
    ) -> None:
        self.config = config
        self.cache = cache
        self._completion = completion

    def complete(self, messages: Messages, schema: type[T]) -> T:
        json_schema = schema.model_json_schema()
        key = cache_key(self.config.model, messages, json_schema)
        if self.cache is not None and (cached := self.cache.get(key)) is not None:
            return schema.model_validate_json(cached)

        conversation = list(messages)
        last_error: Exception | None = None
        for _ in range(2):  # the first try and one retry with the validation error
            text = self._call(conversation, schema, json_schema)
            try:
                answer = schema.model_validate_json(text)
            except ValidationError as exc:
                last_error = exc
                conversation = [
                    *messages,
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": f"Your answer was invalid: {exc}\n"
                        "Reply again with valid JSON that matches the schema.",
                    },
                ]
                continue
            if self.cache is not None:
                self.cache.put(key, answer.model_dump_json())
            return answer
        raise LLMError(f"the model returned an invalid answer twice: {last_error}")

    def _call(self, messages: Messages, schema: type[T], json_schema: dict) -> str:
        try:
            return self._completion(
                model=self.config.model,
                messages=messages,
                api_base=self.config.base_url,
                timeout=self.config.timeout_s,
                temperature=0,
                num_ctx=self.config.num_ctx,
                reasoning_effort="low" if self.config.thinking else "none",
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "schema": json_schema,
                        "strict": True,
                    },
                },
            )
        except Exception as exc:  # LiteLLM raises many provider-specific types
            raise LLMError(
                f"cannot get an answer from {self.config.model} at {self.config.base_url}: {exc}"
            ) from exc


class FakeLLMClient:
    """Test double with the same interface: returns prepared answers in order."""

    def __init__(self, answers: list[BaseModel | dict]) -> None:
        self._answers = list(answers)
        self.calls: list[Messages] = []

    def complete(self, messages: Messages, schema: type[T]) -> T:
        self.calls.append(messages)
        if not self._answers:
            raise LLMError("FakeLLMClient has no prepared answers left")
        answer = self._answers.pop(0)
        data = answer.model_dump() if isinstance(answer, BaseModel) else answer
        return schema.model_validate(json.loads(json.dumps(data)))
