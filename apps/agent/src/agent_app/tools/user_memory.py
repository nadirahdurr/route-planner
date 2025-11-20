from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict


class UserMemoryTool:
    """Extremely simple in-memory store for user-specific context."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = defaultdict(dict)

    def get(self, user_id: str, key: str, default: Any | None = None) -> Any | None:
        return self._store[user_id].get(key, default)

    def set(self, user_id: str, key: str, value: Any) -> None:
        self._store[user_id][key] = value

    def clear(self, user_id: str) -> None:
        self._store.pop(user_id, None)
