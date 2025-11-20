from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ApprovalRequest:
    run_id: str
    summary: str
    options: list[str]


class HumanApprovalTool:
    """Coordinates human-in-the-loop approvals via callbacks to the API layer."""

    def __init__(self) -> None:
        self._pending: dict[str, ApprovalRequest] = {}

    def queue(self, request: ApprovalRequest) -> None:
        self._pending[request.run_id] = request

    def pop(self, run_id: str) -> Optional[ApprovalRequest]:
        return self._pending.pop(run_id, None)

    def list_pending(self) -> list[ApprovalRequest]:
        return list(self._pending.values())
