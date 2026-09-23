"""
认证API - 登录、刷新、用户信息
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from typing import Literal
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.core.config import settings
from app.core.errors import ApiError
from app.db.models.school import School
from app.core.security import (
    create_access_token,
    create_refresh_token,
    commit_token_revocations,
    decode_token,
    ensure_account_environment,
    revoke_session,
    revoke_token,
    validate_token,
    verify_password,
    get_password_hash,
)
from app.db.models.user import Role, User, UserRole
from app.db.models.student import Student
from app.api.deps import get_current_user

router = APIRouter()
optional_security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    school_id: UUID | None = Field(None, description="可选学校范围；默认根据账号和密码自动识别")
    account_type: Literal["teacher", "student", "parent", "general"] | None = None
    identity_id: UUID | None = Field(None, description="凭据对应多个身份时，选择服务端已验证的身份")


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RefreshRequest(BaseModel):
    """刷新Token请求"""
    refresh_token: str


class LogoutRequest(BaseModel):
    """Optional refresh token to revoke alongside the access token."""
    refresh_token: str | None = None


async def _load_roles(db: AsyncSession, user: User) -> list[str]:
    """Load role codes within the user's school scope."""
    result = await db.execute(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user.id,
            UserRole.school_id == user.school_id,
        )
    )
    return [code for code in result.scalars().all() if code]


def account_kind(user, roles):
    if user.account_type != "general":
        return user.account_type
    return next((kind for role, kind in (("TEACHER", "teacher"), ("STUDENT", "student"), ("PARENT", "parent")) if role in roles), "general")


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    用户登录

    返回访问令牌和刷新令牌
    """
    # 查询用户
    user_query = select(User).where(User.username == request.username.strip(), User.status != "deleted")
    if request.school_id is not None:
        user_query = user_query.where(User.school_id == request.school_id)
    if request.account_type is not None:
        role_code = {"teacher": "TEACHER", "student": "STUDENT", "parent": "PARENT"}.get(request.account_type)
        role_ids = select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.code == role_code)
        user_query = user_query.where((User.account_type == request.account_type) | ((User.account_type == "general") & User.id.in_(role_ids)))
    result = await db.execute(user_query)
    candidates = result.scalars().all()
    # Match the supplied credentials before considering role or school. Never
    # guess an account type from a phone number, prefix, or the first DB row.
    matched = []
    for candidate in candidates:
        if await run_in_threadpool(verify_password, request.password, candidate.password_hash):
            matched.append(candidate)
    active = [candidate for candidate in matched if candidate.status == "active"]
    verified = active or matched
    if request.identity_id is not None:
        verified = [candidate for candidate in verified if candidate.id == request.identity_id]
    if not verified:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if len(verified) > 1:
        if not active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户账号已被禁用")
        identities = []
        for candidate in verified:
            await ensure_account_environment(candidate, db)
            candidate_roles = await _load_roles(db, candidate)
            school_name = await db.scalar(select(School.name).where(School.id == candidate.school_id))
            identities.append({"id": str(candidate.id), "display_name": candidate.display_name or candidate.username, "school_name": school_name, "account_type": account_kind(candidate, candidate_roles)})
        raise ApiError(409, "LOGIN_IDENTITY_REQUIRED", "账号和密码已验证，请确认本次登录身份。", details={"identities": identities})
    user = verified[0]

    # 检查用户状态
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户账号已被禁用"
        )

    await ensure_account_environment(user, db)

    # 角色来自关联表，不能把每个登录用户伪装成 STUDENT。
    roles = await _load_roles(db, user)

    # 查询学生信息（如果是学生）
    student_result = await db.execute(
        select(Student).where(
            Student.user_id == user.id,
            Student.school_id == user.school_id,
            Student.status == "active",
        )
    )
    student = student_result.scalar_one_or_none()

    # 生成Token
    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "school_id": str(user.school_id),
        "roles": roles,
        "password_version": user.password_version,
        "sid": str(uuid4()),
        "session_exp": int((datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
    }

    if student:
        token_data["student_id"] = str(student.id)

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # 更新最后登录时间
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": str(user.id),
            "username": user.username,
            "display_name": user.display_name or user.username,
            "roles": roles,
            "account_type": account_kind(user, roles),
            "student_id": str(student.id) if student else None,
            "must_change_password": user.must_change_password,
        }
    )


@router.post("/refresh")
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    刷新访问令牌
    """
    payload = await validate_token(request.refresh_token, db, expected_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌"
        )

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
        )

    try:
        user_id = UUID(str(subject))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.status != "active" or payload.get("password_version", 0) != user.password_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户账号不可用",
        )

    await ensure_account_environment(user, db)

    roles = await _load_roles(db, user)
    student_result = await db.execute(
        select(Student).where(
            Student.user_id == user.id,
            Student.school_id == user.school_id,
            Student.status == "active",
        )
    )
    student = student_result.scalar_one_or_none()

    # The unique revocation key atomically consumes the submitted token.
    # Commit before issuing a replacement so a concurrent worker cannot also
    # rotate it, and a restart never resurrects an acknowledged credential.
    if not await revoke_token(request.refresh_token, db, expected_type="refresh"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌已被使用，请重新登录",
            headers={"X-Error-Code": "REFRESH_TOKEN_REUSED"},
        )
    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "school_id": str(user.school_id),
        "roles": roles,
        "password_version": user.password_version,
        "sid": payload["sid"],
        "session_exp": payload["session_exp"],
    }
    if student:
        token_data["student_id"] = str(student.id)

    await commit_token_revocations(db)
    new_access_token = create_access_token(token_data)

    return {
        "access_token": new_access_token,
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: LogoutRequest | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
    db: AsyncSession = Depends(get_db),
):
    """Idempotently revoke only the caller's presented credentials.

    Verify signatures even on repeat/expired logout, but do not require an
    unrevoked token: that would turn the second identical logout into a 401.
    """
    access_token = credentials.credentials if credentials else None
    refresh = request.refresh_token if request else None
    access_payload = decode_token(access_token, expected_type="access", allow_expired=True) if access_token else None
    refresh_payload = decode_token(refresh, expected_type="refresh", allow_expired=True) if refresh else None
    if (access_token and not access_payload) or (refresh and not refresh_payload) or not (access_payload or refresh_payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法验证退出凭据",
            headers={"X-Error-Code": "INVALID_LOGOUT_TOKEN"},
        )
    if any(not payload.get("sub") for payload in (access_payload, refresh_payload) if payload):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无法验证退出凭据")
    if access_payload and refresh_payload and access_payload["sub"] != refresh_payload["sub"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不能撤销其他账号的凭据",
            headers={"X-Error-Code": "LOGOUT_TOKEN_OWNER_MISMATCH"},
        )
    if access_payload and refresh_payload and access_payload["sid"] != refresh_payload["sid"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="退出凭据不属于同一登录会话",
            headers={"X-Error-Code": "LOGOUT_SESSION_MISMATCH"},
        )
    if access_token:
        await revoke_token(access_token, db, expected_type="access", allow_expired=True)
    if refresh:
        await revoke_token(refresh, db, expected_type="refresh", allow_expired=True)
    await revoke_session(access_payload or refresh_payload, db)
    await commit_token_revocations(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=72)


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(select(User).where(User.id == current.user_id).with_for_update().execution_options(populate_existing=True))
    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确。")
    if request.new_password == user.username or verify_password(request.new_password, user.password_hash) or len(request.new_password.encode()) > 72:
        raise HTTPException(status_code=422, detail="新密码不能与账号或当前密码相同，长度为 8–72 字节。")
    user.password_hash = get_password_hash(request.new_password)
    user.must_change_password = False
    user.password_version += 1
    from app.services.education_common import audit
    audit(db, current, "account.password_change", user)
    await db.commit()
    token_data = {"sub": str(user.id), "username": user.username, "school_id": str(user.school_id), "roles": await _load_roles(db, user), "password_version": user.password_version, "sid": str(uuid4())}
    return {"access_token": create_access_token(token_data), "refresh_token": create_refresh_token(token_data), "token_type": "bearer", "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60}


@router.get("/me")
async def get_current_user_info(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取当前用户信息
    """
    # 查询完整用户信息
    result = await db.execute(
        select(User).where(User.id == current_user.user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    # 查询学生信息
    student = None
    student_data = None
    if current_user.has_role("STUDENT"):
        student_result = await db.execute(
            select(Student).where(
                Student.user_id == user.id,
                Student.school_id == user.school_id,
                Student.status == "active",
            )
        )
        student = student_result.scalar_one_or_none()

        if student:
            student_data = {
                "id": str(student.id),
                "name": student.name,
                "student_no": student.student_no,
            }

    return {
        "user_id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "school_id": str(user.school_id),
        "roles": current_user.roles,
        "must_change_password": user.must_change_password,
        "account_type": account_kind(user, current_user.roles),
        "student": student_data
    }
