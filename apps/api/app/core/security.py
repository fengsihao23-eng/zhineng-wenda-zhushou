"""
JWT安全模块
"""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from hashlib import sha256
from math import isfinite
from typing import Optional
from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from uuid import uuid4
from passlib.exc import UnknownHashError

from app.core.config import settings
from app.db.models.school import School
from app.db.models.security import TokenRevocation
from app.db.models.user import User

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEMO_USERNAMES = frozenset({
    "student_basic", "student_diagnosis", "student1", "student2",
    "teacher_demo", "school_admin_demo", "city_operator_demo",
})


def _revocation_store_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="登录安全状态暂时不可用，请稍后重试",
        headers={"X-Error-Code": "TOKEN_REVOCATION_UNAVAILABLE"},
    )


async def ensure_account_environment(user: User, db: AsyncSession) -> None:
    """Block fixture identities in deployed environments, including tokens
    issued before switching the deployment out of development mode.
    """
    if settings.demo_accounts_allowed:
        return
    is_demo = user.username.casefold() in DEMO_USERNAMES
    if not is_demo:
        school_code = await db.scalar(select(School.code).where(School.id == user.school_id))
        is_demo = bool(school_code and school_code.casefold() == "demo_school")
    # Legacy fixtures can have been renamed or attached to another school.
    # Compare against the known development default without exposing hashes
    # or credentials; a migrated default credential must be reset first.
    if not is_demo:
        try:
            is_demo = _has_default_password(user.password_hash)
        except (UnknownHashError, ValueError, TypeError):
            is_demo = True  # Unknown stored credentials must not authenticate.
    if is_demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="示例账号不能用于当前环境，请使用正式授权账号",
            headers={"X-Error-Code": "DEMO_ACCOUNT_DISABLED"},
        )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (UnknownHashError, ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)


@lru_cache(maxsize=2048)
def _has_default_password(password_hash: str) -> bool:
    # Cache by immutable hash, not user ID: a changed credential is rechecked
    # immediately, without repeating bcrypt on every authenticated request.
    return pwd_context.verify("password123", password_hash)


def _session_claims(data: dict) -> dict:
    claims = data.copy()
    claims.setdefault("sid", str(uuid4()))
    claims.setdefault(
        "session_exp",
        int((datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
    )
    return claims


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """创建访问令牌"""
    to_encode = _session_claims(data)

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    expire = min(expire, datetime.fromtimestamp(to_encode["session_exp"], tz=timezone.utc))
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
    to_encode = _session_claims(data)

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )

    expire = min(expire, datetime.fromtimestamp(to_encode["session_exp"], tz=timezone.utc))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "jti": str(uuid4()), "type": "refresh"})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt


def decode_token(
    token: str,
    expected_type: str | None = None,
    *,
    allow_expired: bool = False,
) -> dict:
    """Verify signature/claims only; authorization must use ``validate_token``.

    Expired signed credentials are accepted only by idempotent logout, never
    by normal authentication or refresh. Tokens without a revocable ID fail
    closed instead of remaining valid until their expiry.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": not allow_expired},
        )
        if expected_type and payload.get("type") != expected_type:
            return {}
        if payload.get("type") not in {"access", "refresh"}:
            return {}
        if not isinstance(payload.get("jti"), str) or not payload["jti"]:
            return {}
        # Pre-migration tokens cannot be tied to a logout session, so require
        # reauthentication instead of leaving old access credentials usable.
        if not isinstance(payload.get("sid"), str) or not payload["sid"]:
            return {}
        expiry = payload.get("exp")
        if isinstance(expiry, bool) or not isinstance(expiry, (int, float)) or not isfinite(expiry):
            return {}
        session_expiry = payload.get("session_exp")
        if isinstance(session_expiry, bool) or not isinstance(session_expiry, (int, float)) or not isfinite(session_expiry):
            return {}
        if expiry > session_expiry or (not allow_expired and session_expiry <= datetime.now(timezone.utc).timestamp()):
            return {}
        return payload
    except (JWTError, TypeError, ValueError):
        return {}


async def validate_token(token: str, db: AsyncSession, expected_type: str | None = None) -> dict:
    """Verify a token against the durable store on every authorization check."""
    payload = decode_token(token, expected_type=expected_type)
    if not payload or await is_token_revoked(payload, db):
        return {}
    return payload


def _token_id_hash(payload: dict) -> str:
    # Include type so identifier domains stay separate. Never persist raw JWTs.
    return sha256(f"{payload['type']}:{payload['jti']}".encode("utf-8")).hexdigest()


def _session_id_hash(payload: dict) -> str:
    return sha256(f"session:{payload['sid']}".encode("utf-8")).hexdigest()


async def _insert_revocation(db: AsyncSession, identifier: str, token_type: str, expiry: float) -> bool:
    try:
        dialect = db.get_bind().dialect.name
        insert = {"postgresql": postgresql_insert, "sqlite": sqlite_insert}.get(dialect)
        if insert is None:
            raise _revocation_store_unavailable()
        statement = insert(TokenRevocation).values(
            token_id_hash=identifier,
            token_type=token_type,
            expires_at=datetime.fromtimestamp(expiry, tz=timezone.utc),
        ).on_conflict_do_nothing(index_elements=["token_id_hash"]).returning(TokenRevocation.token_id_hash)
        result = await db.execute(statement)
        return result.scalar_one_or_none() is not None
    except SQLAlchemyError:
        raise _revocation_store_unavailable() from None


async def revoke_token(
    token: str,
    db: AsyncSession,
    expected_type: str | None = None,
    *,
    allow_expired: bool = False,
) -> bool:
    """Atomically consume a token; return False on an existing revocation.

    The caller must commit before reporting success/issuing a replacement.
    Concurrent workers use a unique database key, not a check-then-write race.
    No process-local or cache fallback may admit revoked credentials.
    """
    payload = decode_token(token, expected_type=expected_type, allow_expired=allow_expired)
    if not payload:
        return False
    if payload["exp"] <= datetime.now(timezone.utc).timestamp():
        # An expired token is already unusable; logout remains idempotent.
        return True
    return await _insert_revocation(db, _token_id_hash(payload), payload["type"], payload["exp"])


async def revoke_session(payload: dict, db: AsyncSession) -> bool:
    """Invalidate every access/refresh token minted for this login session."""
    if payload["session_exp"] <= datetime.now(timezone.utc).timestamp():
        return True
    return await _insert_revocation(db, _session_id_hash(payload), "session", payload["session_exp"])


async def commit_token_revocations(db: AsyncSession) -> None:
    """Acknowledgement must follow a durable commit, not an in-memory flush."""
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise _revocation_store_unavailable() from None


async def is_token_revoked(payload: dict, db: AsyncSession) -> bool:
    """Return whether the decoded token's identifier has been revoked."""
    if not payload.get("jti") or not payload.get("sid") or payload.get("type") not in {"access", "refresh"}:
        return True
    try:
        revoked = await db.scalar(
            select(TokenRevocation.token_id_hash).where(
                TokenRevocation.token_id_hash.in_([_token_id_hash(payload), _session_id_hash(payload)])
            ).limit(1)
        )
        return revoked is not None
    except SQLAlchemyError:
        raise _revocation_store_unavailable() from None
