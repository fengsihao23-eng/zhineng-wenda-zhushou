"""Compatibility entry point for the unified agent execution pipeline.

Historically the project had two independent loops. Keeping a second copy
made fixes to tracing, prompts, and guards diverge. ``EnhancedAgentLoop`` now
only adapts the old constructor/signature to :class:`AgentLoop`.
"""
from __future__ import annotations

from typing import AsyncGenerator
from uuid import UUID, uuid4

from app.agent.agent_loop import AgentLoop, AgentResponse
from app.core.prompt_registry import PromptRegistry
from app.schemas.guard import GuardConfig
from app.ai.gateway import ModelGateway
from app.tools.registry import ToolRegistry


class EnhancedAgentLoop(AgentLoop):
    """Backward-compatible facade over the single production AgentLoop."""

    def __init__(
        self,
        db,
        model_gateway: ModelGateway,
        tool_registry: ToolRegistry,
        prompt_registry: PromptRegistry | None = None,
        guard_config: GuardConfig | None = None,
    ) -> None:
        super().__init__(
            db=db,
            tool_registry=tool_registry,
            model_gateway=model_gateway,
            prompt_registry=prompt_registry,
        )
        if guard_config is not None:
            from app.core.response_guard import ResponseGuard

            self.response_guard = ResponseGuard(guard_config)

    async def run(
        self,
        student_id: UUID,
        school_id: UUID,
        query: str,
        session_id: UUID | None = None,
        stream: bool = False,
        user_id: UUID | None = None,
        request_id: str | None = None,
        chat_history: list[dict] | None = None,
    ) -> AgentResponse | AsyncGenerator[dict, None]:
        kwargs = {
            "user_query": query,
            "student_id": student_id,
            "school_id": school_id,
            "user_id": user_id or student_id,
            "request_id": request_id or str(uuid4()),
            "chat_history": chat_history,
            "session_id": session_id,
        }
        if stream:
            return super().run_stream(**kwargs)
        return await super().run(**kwargs)
