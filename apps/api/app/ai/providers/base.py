"""
Provider基类
"""
from abc import ABC, abstractmethod
from typing import AsyncIterator
from decimal import Decimal

from app.ai.schemas import ModelResponse, ModelChunk, Usage


class BaseProvider(ABC):
    """Provider基类"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def estimate_cost(self, usage: Usage, model: str) -> Decimal:
        """估算成本"""
        pass
