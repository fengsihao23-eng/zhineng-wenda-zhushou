"""
DeepSeek Provider
"""
from decimal import Decimal
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.core.config import settings


class DeepSeekProvider(OpenAICompatibleProvider):
    """DeepSeek专用Provider"""

    def __init__(self, api_key: str):
        super().__init__(
            name="DeepSeek",
            base_url=settings.DEEPSEEK_API_BASE,
            api_key=api_key,
            default_model="deepseek-chat",
            price_per_1k_input=Decimal("0.0001"),
            price_per_1k_output=Decimal("0.0002")
        )
