from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowState:
    """Temporary state for one Manager planning execution."""

    request_id: str
    user_state: Any

    candidate_recipe_ids: list[str] = field(default_factory=list)
    candidate_results: dict[str, Any] = field(default_factory=dict)

    selected_recipe_id: str | None = None

    status: str = "running"

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    execution_trace: list[dict[str, Any]] = field(default_factory=list)

    def trace(
        self,
        step: str,
        **details: Any,
    ) -> None:
        """Add one event to the workflow execution trace."""

        event = {
            "step": step,
            **details,
        }

        self.execution_trace.append(event)