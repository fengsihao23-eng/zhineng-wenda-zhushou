"""The deterministic model must be opt-in rather than an implicit fallback."""
import pytest

from app.ai.gateway import ModelGateway, ModelProviderUnavailableError
from app.core.config import settings


def test_fake_provider_is_explicit(monkeypatch):
    monkeypatch.setattr(settings, "MODEL_PROVIDER", "fake")
    gateway = ModelGateway()
    assert gateway.runtime_status["test_model_enabled"] is True
    assert gateway.runtime_status["real_model_ready"] is False


@pytest.mark.asyncio
async def test_missing_real_provider_fails_loudly(monkeypatch):
    monkeypatch.setattr(settings, "MODEL_PROVIDER", "auto")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
    gateway = ModelGateway()
    with pytest.raises(ModelProviderUnavailableError, match="没有可用的真实大模型"):
        await gateway.chat(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])
