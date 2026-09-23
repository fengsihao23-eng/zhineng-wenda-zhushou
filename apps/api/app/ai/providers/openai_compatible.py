"""
OpenAI兼容Provider
"""
import time
import json
from typing import AsyncIterator
from decimal import Decimal
from openai import AsyncOpenAI

from app.ai.providers.base import BaseProvider
from app.ai.schemas import ModelResponse, ModelChunk, Usage, ToolCall


class OpenAICompatibleProvider(BaseProvider):
    """OpenAI兼容Provider"""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
        price_per_1k_input: Decimal,
        price_per_1k_output: Decimal,
        extra_body: dict | None = None,
    ):
        super().__init__(name)
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
        )
        self.extra_body = extra_body
        self.default_model = default_model
        self.price_input = price_per_1k_input
        self.price_output = price_per_1k_output

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs
    ) -> ModelResponse:
        """同步调用"""
        start = time.time()

        params = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            params["max_tokens"] = max_tokens

        if tools:
            params["tools"] = tools

        if self.extra_body is not None:
            params["extra_body"] = self.extra_body
        response = await self.client.chat.completions.create(**params)

        latency_ms = int((time.time() - start) * 1000)

        return self._normalize_response(response, latency_ms)

    async def stream(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs
    ) -> AsyncIterator[ModelChunk]:
        """流式调用"""
        params = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens:
            params["max_tokens"] = max_tokens

        if tools:
            params["tools"] = tools

        if self.extra_body is not None:
            params["extra_body"] = self.extra_body
        stream = await self.client.chat.completions.create(**params)

        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield ModelChunk(
                        text=delta.content,
                        finish_reason=chunk.choices[0].finish_reason,
                    )

    def _normalize_response(
        self,
        raw_response,
        latency_ms: int
    ) -> ModelResponse:
        """标准化响应"""
        choice = raw_response.choices[0]
        message = choice.message

        # 提取tool_calls
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    type="function",
                    function={
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    },
                ))

        content = message.content or ""
        return ModelResponse(
            content=content,
            text=content,
            tool_calls=tool_calls,
            usage=Usage(
                prompt_tokens=raw_response.usage.prompt_tokens,
                completion_tokens=raw_response.usage.completion_tokens,
                total_tokens=raw_response.usage.total_tokens
            ),
            provider=self.name,
            model=raw_response.model,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason
        )

    def estimate_cost(self, usage: Usage, model: str) -> Decimal:
        """估算成本"""
        input_cost = (Decimal(usage.prompt_tokens) / 1000) * self.price_input
        output_cost = (Decimal(usage.completion_tokens) / 1000) * self.price_output
        return input_cost + output_cost
