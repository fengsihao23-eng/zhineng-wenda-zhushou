"""
核心配置
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Union, Literal
from pydantic import Field, field_validator, model_validator
from secrets import token_urlsafe


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    # 应用基础配置
    APP_NAME: str = "StudentAgent"
    APP_ENV: str = "development"
    DEBUG: bool = False
    # Demo/test identities are available only for local development by default.
    ENABLE_TEST_ACCOUNTS: bool = True
    SECRET_KEY: str = Field(default_factory=lambda: token_urlsafe(48))

    # 数据库配置
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/testdb"

    # Redis 配置
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT 配置
    JWT_SECRET_KEY: str = Field(default_factory=lambda: token_urlsafe(48))
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # CORS 配置
    CORS_ORIGINS: Union[str, List[str]] = "http://localhost:3000,http://localhost"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # 模型配置
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-flash"
    DEEPSEEK_THINKING: Literal["enabled", "disabled"] = "disabled"
    # ``fake`` is an explicit test-only mode.  ``auto`` selects the first
    # configured real provider and never silently falls back to fake.
    MODEL_PROVIDER: str = "auto"

    DEFAULT_MODEL: str = "gpt-4o-mini"
    DEFAULT_TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2000

    # Agent 配置
    MAX_TOOL_ITERATIONS: int = 5
    AGENT_TIMEOUT_SECONDS: int = 30

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "/app/logs/app.log"

    # 限流配置
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000

    # SSE 配置
    SSE_HEARTBEAT_INTERVAL: int = 15
    SSE_TIMEOUT: int = 300

    @property
    def demo_accounts_allowed(self) -> bool:
        """Only explicitly local/test environments may use fixture identities."""
        return self.APP_ENV.lower() in {"development", "test"} and self.ENABLE_TEST_ACCOUNTS

    def require_demo_environment(self) -> None:
        """Stop seed scripts before opening a connection to deployed data."""
        if not self.demo_accounts_allowed:
            raise RuntimeError("示例账号和数据仅允许在 development/test 环境初始化")

    @model_validator(mode="after")
    def validate_security_settings(self):
        """Reject placeholder credentials before a production process starts.

        Development and test environments intentionally keep usable defaults
        so local setup remains simple.  Production-like environments must
        provide two independent, sufficiently long secrets.
        """
        if self.APP_ENV.lower() not in {"development", "test"}:
            self.ENABLE_TEST_ACCOUNTS = False
            weak_values = {
                "default_secret_key_for_dev",
                "default_jwt_secret_key_minimum_32_chars",
                "change-me",
                "changeme",
                "your-secret-key",
                "your-super-secret-key-change-this-in-production",
                "replace-with-a-random-32-byte-secret",
            }
            for name in ("SECRET_KEY", "JWT_SECRET_KEY"):
                value = getattr(self, name, "")
                normalized = value.lower()
                if (
                    name not in self.model_fields_set
                    or
                    not value
                    or len(value) < 32
                    or normalized in weak_values
                    or normalized.startswith("dev_")
                    or normalized.startswith("test_")
                    or "testing" in normalized
                    or normalized.startswith(("your_", "your-", "replace-with", "change-this"))
                ):
                    raise ValueError(
                        f"{name} must be a unique secret of at least 32 characters "
                        "in production/staging"
                    )
            if self.SECRET_KEY == self.JWT_SECRET_KEY:
                raise ValueError("SECRET_KEY and JWT_SECRET_KEY must be different")
        return self

settings = Settings()
