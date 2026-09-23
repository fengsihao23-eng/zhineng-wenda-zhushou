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
            default_model=settings.DEEPSEEK_MODEL,
            # Flash peak, cache-miss ceiling estimate (USD / 1K); actual billing
            # varies with cache hits and peak/off-peak hours.
            price_per_1k_input=Decimal("0.0003"),
            price_per_1k_output=Decimal("0.0012"),
            extra_body={"thinking": {"type": settings.DEEPSEEK_THINKING}},
        )
