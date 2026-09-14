"""
JWT安全模块
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from uuid import uuid4

from app.core.config import settings

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# A small process-local revocation registry keeps logout and refresh rotation
# deterministic during local development.  Production deployments should
# replace this with a shared Redis-backed store before running multiple API
# workers; the API surface is intentionally kept behind these helpers.
_revoked_tokens: dict[str, float] = {}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """创建访问令牌"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "jti": str(uuid4()), "type": "access"})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt


def create_refresh_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """创建刷新令牌"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )

    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "jti": str(uuid4()), "type": "refresh"})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt


def decode_token(token: str, expected_type: str | None = None) -> dict:
    """解码令牌并可选地校验 access/refresh 类型和撤销状态。"""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        if expected_type and payload.get("type") != expected_type:
            return {}
        if is_token_revoked(payload):
            return {}
        return payload
    except JWTError:
        return {}


def revoke_token(token: str) -> bool:
    """Revoke a token until its natural expiry.

    The registry is process-local by design for the current single-worker
    deployment.  A shared store must be used when scaling horizontally.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
    except JWTError:
        return False

    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or exp is None:
        return False
    _revoked_tokens[str(jti)] = float(exp)
    _purge_revoked_tokens()
    return True


def is_token_revoked(payload: dict) -> bool:
    """Return whether a decoded token's JTI has been revoked."""
    _purge_revoked_tokens()
    jti = payload.get("jti")
    return bool(jti and str(jti) in _revoked_tokens)


def _purge_revoked_tokens() -> None:
    now = datetime.now(timezone.utc).timestamp()
    expired = [jti for jti, exp in _revoked_tokens.items() if exp <= now]
    for jti in expired:
        _revoked_tokens.pop(jti, None)
