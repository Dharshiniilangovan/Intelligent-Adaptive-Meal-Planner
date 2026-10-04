"""Shared contracts used by all Day-4 agents.

Keep these contracts small and stable. Business logic belongs in the
existing deterministic services; agents only orchestrate those services.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class AgentStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(slots=True)
class AgentResult:
    agent: str
    status: AgentStatus | str
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = AgentStatus(self.status)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        return result


def normalize_agent_result(result: AgentResult | dict[str, Any], expected_agent: str) -> dict[str, Any]:
    """Return a validated plain-dict result.

    This lets the Manager accept either AgentResult instances or plain dicts,
    which makes integration with independently developed agents easier.
    """
    if isinstance(result, AgentResult):
        result = result.to_dict()

    if not isinstance(result, dict):
        raise TypeError(f"{expected_agent} agent must return AgentResult or dict")

    normalized = {
        "agent": result.get("agent", expected_agent),
        "status": result.get("status"),
        "data": result.get("data", {}),
        "warnings": list(result.get("warnings", [])),
        "errors": list(result.get("errors", [])),
    }

    if normalized["agent"] != expected_agent:
        raise ValueError(
            f"Expected agent='{expected_agent}', got agent='{normalized['agent']}'"
        )

    if normalized["status"] not in {s.value for s in AgentStatus}:
        raise ValueError(
            f"Invalid {expected_agent} status: {normalized['status']!r}"
        )

    if not isinstance(normalized["data"], dict):
        raise TypeError(f"{expected_agent} result data must be a dictionary")

    return normalized
