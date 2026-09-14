"""用于本地开发、自动化测试和无外部模型凭据环境的确定性 Provider。"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import AsyncIterator

from app.ai.providers.base import BaseProvider
from app.ai.schemas import ModelChunk, ModelResponse, Usage


class FakeModelProvider(BaseProvider):
    def __init__(self, name: str = "Fake"):
        super().__init__(name)

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> ModelResponse:
        answer = self._answer(messages)
        tokens = max(1, len(answer))
        return ModelResponse(
            content=answer,
            text=answer,
            tool_calls=None,
            usage=Usage(
                prompt_tokens=sum(len(str(item.get("content", ""))) for item in messages),
                completion_tokens=tokens,
                total_tokens=tokens + sum(len(str(item.get("content", ""))) for item in messages),
            ),
            provider=self.name,
            model=model or "fake-model",
            latency_ms=1,
            finish_reason="stop",
        )

    async def stream(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> AsyncIterator[ModelChunk]:
        answer = self._answer(messages)
        for index in range(0, len(answer), 20):
            yield ModelChunk(text=answer[index:index + 20])
        yield ModelChunk(text="", finish_reason="stop")

    def estimate_cost(self, usage: Usage, model: str) -> Decimal:
        return Decimal("0")

    @staticmethod
    def _answer(messages: list[dict]) -> str:
        tool_messages = [
            item
            for item in messages
            if item.get("role") == "tool" or str(item.get("content", "")).startswith("[TOOL_RESULT]")
        ]
        if not tool_messages:
            user_message = next(
                (item.get("content", "") for item in reversed(messages) if item.get("role") == "user"),
                "",
            )
            return f"我已收到你的问题：{user_message}。当前试点环境使用确定性回答模型。"

        raw = tool_messages[-1].get("content", "").removeprefix("[TOOL_RESULT] ")
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return "已查询到学习数据，但结果暂时无法整理。"
        if isinstance(data, dict) and data:
            pairs = []
            for key, value in list(data.items())[:6]:
                if isinstance(value, (str, int, float)):
                    pairs.append(f"{key}：{value}")
            if pairs:
                return "根据你的学习数据：" + "；".join(pairs) + "。"
        return "已查询到学习数据，请结合来源记录查看详情。"
