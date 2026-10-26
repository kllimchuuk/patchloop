"""On-disk cache of LLM answers, keyed by a hash of everything that shapes the answer."""

import hashlib
import json
from pathlib import Path


def cache_key(model: str, messages: list[dict[str, str]], schema: dict) -> str:
    payload = json.dumps(
        {"model": model, "messages": messages, "schema": schema},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AnswerCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def get(self, key: str) -> str | None:
        path = self.root / f"{key}.json"
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def put(self, key: str, text: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / f"{key}.json").write_text(text, encoding="utf-8")
