"""
认证API - 登录、刷新、用户信息
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from uuid import UUID

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_token,
    verify_password,
)
from app.db.models.user import Role, User, UserRole
from app.db.models.student import Student
from app.api.deps import AuthenticatedUser, get_current_user

router = APIRouter()
optional_security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    school_id: UUID | None = Field(None, description="学校ID；多校同名账号时必填")


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
    user_query = select(User).where(User.username == request.username)
    if request.school_id is not None:
        user_query = user_query.where(User.school_id == request.school_id)
    result = await db.execute(user_query)
    candidates = result.scalars().all()
    # Usernames are unique only inside a school.  Never select an arbitrary
    # tenant when a caller omits school_id and names collide.
    user = candidates[0] if len(candidates) == 1 else None

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # 验证密码
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # 检查用户状态
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户账号已被禁用"
        )

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
        "roles": roles
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
        expires_in=3600,  # 1小时
        user={
            "id": str(user.id),
            "username": user.username,
            "display_name": user.display_name or user.username,
            "roles": roles,
            "student_id": str(student.id) if student else None
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
    payload = decode_token(request.refresh_token, expected_type="refresh")
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
    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户账号不可用",
        )

    roles = await _load_roles(db, user)
    student_result = await db.execute(
        select(Student).where(
            Student.user_id == user.id,
            Student.school_id == user.school_id,
            Student.status == "active",
        )
    )
    student = student_result.scalar_one_or_none()

    # Rotate the refresh token: the submitted token cannot be replayed.
    revoke_token(request.refresh_token)

    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "school_id": str(user.school_id),
        "roles": roles,
    }
    if student:
        token_data["student_id"] = str(student.id)

    new_access_token = create_access_token(token_data)

    return {
        "access_token": new_access_token,
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
        "expires_in": 3600
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: LogoutRequest | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Revoke the presented access token for this process lifetime."""
    # The dependency has already validated the token.  Read the raw header
    # again so the token can be added to the revocation registry.
    if credentials is not None:
        revoke_token(credentials.credentials)
    if request and request.refresh_token:
        revoke_token(request.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
        "student": student_data
    }
