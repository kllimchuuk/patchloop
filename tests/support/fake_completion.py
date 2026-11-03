"""A scripted stand-in for the LiteLLM completion call, for tests of the real `LiteLLMClient`."""

from typing import Any


class ScriptedCompletion:
    """Returns (or raises) the prepared items in order and records every call."""

    def __init__(self, items: list[Any]) -> None:
        self.items = list(items)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
