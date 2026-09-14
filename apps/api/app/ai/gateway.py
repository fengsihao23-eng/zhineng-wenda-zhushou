"""
Model Gateway
"""
import asyncio
import logging
from typing import AsyncIterator, Optional
from decimal import Decimal

from app.ai.providers.base import BaseProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.providers.deepseek import DeepSeekProvider
from app.ai.providers.fake import FakeModelProvider
from app.ai.schemas import ModelResponse, ModelChunk, Usage
from app.core.config import settings

logger = logging.getLogger(__name__)


class ModelProviderUnavailableError(RuntimeError):
    """Raised when production chat has no configured real model provider."""

_PLACEHOLDER_KEYS = {
    "your-openai-api-key",
    "your-openai-api-key-here",
    "your-openai-api-key-here-minimum-32-characters",
    "your-deepseek-api-key",
    "your_deepseek_api_key",
    "your_openai_api_key",
}


def _usable_key(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return bool(normalized) and normalized not in _PLACEHOLDER_KEYS and not normalized.startswith("your-") and not normalized.startswith("your_")


class ModelGateway:
    """模型调用网关"""

    def __init__(self):
        self.providers: dict[str, BaseProvider] = {}
        self._initialize_providers()

    def _initialize_providers(self):
        """初始化Providers"""
        mode = getattr(settings, "MODEL_PROVIDER", "auto").lower().strip()
        if mode == "fake":
            self.providers["fake"] = FakeModelProvider()
            return
        if mode not in {"auto", "openai", "deepseek"}:
            raise ValueError("MODEL_PROVIDER must be one of auto, openai, deepseek, fake")
        # DeepSeek Provider
        if _usable_key(settings.DEEPSEEK_API_KEY) and mode in {"auto", "deepseek"}:
            self.providers["deepseek"] = DeepSeekProvider(
                api_key=settings.DEEPSEEK_API_KEY
            )
            logger.info("DeepSeek provider initialized")

        # OpenAI Provider
        if _usable_key(settings.OPENAI_API_KEY) and mode in {"auto", "openai"}:
            self.providers["openai"] = OpenAICompatibleProvider(
                name="OpenAI",
                base_url=settings.OPENAI_API_BASE,
                api_key=settings.OPENAI_API_KEY,
                default_model="gpt-4o-mini",
                price_per_1k_input=Decimal("0.00015"),
                price_per_1k_output=Decimal("0.0006")
            )
            logger.info("OpenAI provider initialized")

        if not self.providers:
            logger.error(
                "no_real_model_provider_configured",
                extra={"model_provider": mode, "hint": "Set OPENAI_API_KEY or DEEPSEEK_API_KEY; use MODEL_PROVIDER=fake only in tests."},
            )

    def _get_provider(self, model: str) -> BaseProvider:
        """根据模型名称获取Provider"""
        # 简单的路由逻辑
        if model.lower().startswith("fake"):
            provider = self.providers.get("fake")
        elif "deepseek" in model.lower():
            provider = self.providers.get("deepseek")
        elif "gpt" in model.lower():
            provider = self.providers.get("openai")
        else:
            # 默认使用第一个可用的provider
            provider = next(iter(self.providers.values()), None)

        # If a configured model has no matching credential, use the configured
        # local fallback instead of failing with an opaque provider error.
        if not provider:
            provider = next(iter(self.providers.values()), None)
        if not provider:
            raise ModelProviderUnavailableError(
                "没有可用的真实大模型 Provider。请配置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY；"
                "仅在测试环境显式设置 MODEL_PROVIDER=fake。"
            )

        return provider

    async def chat(
        self,
        model: str = "deepseek-chat",
        messages: list = None,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: int = 30,
        trace_context: dict | None = None
    ) -> ModelResponse:
        """统一对话调用"""
        provider = self._get_provider(model)

        # 转换ChatMessage对象为dict
        message_dicts = []
        for msg in messages:
            if hasattr(msg, 'dict'):
                msg_dict = msg.dict(exclude_none=True)
            elif isinstance(msg, dict):
                msg_dict = msg
            else:
                msg_dict = {"role": msg.role, "content": msg.content}
            message_dicts.append(msg_dict)

        try:
            response = await asyncio.wait_for(
                provider.chat(
                    model=self._model_for_provider(provider, model),
                    messages=message_dicts,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=timeout
            )

            # 记录使用情况
            if trace_context:
                await self._track_usage(
                    provider=provider,
                    model=model,
                    usage=response.usage,
                    trace_context=trace_context,
                )

            return response

        except asyncio.TimeoutError:
            logger.error(f"Model call timeout after {timeout}s")
            raise
        except Exception as e:
            logger.error(f"Model call failed: {e}")
            raise

    async def stream(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: int = 30,
        trace_context: dict | None = None
    ) -> AsyncIterator[ModelChunk]:
        """流式对话调用"""
        provider = self._get_provider(model)

        try:
            async for chunk in provider.stream(
                model=self._model_for_provider(provider, model),
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield chunk

        except Exception as e:
            logger.error(f"Model stream failed: {e}")
            raise

    @staticmethod
    def _model_for_provider(provider: BaseProvider, model: str) -> str:
        """Avoid sending a GPT model name to a DeepSeek endpoint in auto mode."""
        default_model = getattr(provider, "default_model", None)
        if default_model and provider.name.lower().startswith("deepseek") and "deepseek" not in (model or "").lower():
            return default_model
        if default_model and provider.name.lower().startswith("openai") and "deepseek" in (model or "").lower():
            return default_model
        return model

    @property
    def runtime_status(self) -> dict[str, object]:
        configured = settings.MODEL_PROVIDER.lower()
        available = list(self.providers.keys())
        return {
            "configured_provider": configured,
            "available_providers": available,
            "real_model_ready": any(name != "fake" for name in available),
            "test_model_enabled": "fake" in available,
        }

    async def structured(
        self,
        model: str,
        messages: list[dict],
        response_schema: dict,
        temperature: float = 0.1,
        timeout: int = 30,
        trace_context: dict | None = None
    ) -> dict:
        """结构化输出调用"""
        # 在消息中添加schema要求
        system_message = {
            "role": "system",
            "content": f"You must respond with a valid JSON object matching this schema: {response_schema}"
        }

        enhanced_messages = [system_message] + messages

        response = await self.chat(
            model=model,
            messages=enhanced_messages,
            temperature=temperature,
            timeout=timeout,
            trace_context=trace_context,
        )

        # 尝试解析JSON
        import json
        try:
            return json.loads(response.text)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse structured response: {response.text}")
            raise ValueError("Model did not return valid JSON")

    async def _track_usage(
        self,
        provider: BaseProvider,
        model: str,
        usage: Usage,
        trace_context: dict,
    ):
        """追踪使用情况"""
        # TODO: 记录到数据库
        logger.info(
            f"Model usage: provider={provider.name}, model={model}, "
            f"tokens={usage.total_tokens}, "
            f"agent_run_id={trace_context.get('agent_run_id')}"
        )


# 全局单例
_gateway: Optional[ModelGateway] = None


def get_model_gateway() -> ModelGateway:
    """获取ModelGateway单例"""
    global _gateway
    if _gateway is None:
        _gateway = ModelGateway()
    return _gateway
