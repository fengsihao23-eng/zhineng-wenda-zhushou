"""
认证依赖
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.core.database import get_db
from app.core.security import decode_token
from app.db.models.user import Role, User, UserRole
from app.db.models.student import Student

security = HTTPBearer(auto_error=False)


class AuthenticatedUser:
    """认证用户"""
    def __init__(
        self,
        user_id: UUID,
        school_id: UUID,
        username: str,
        roles: list[str],
    ):
        self.user_id = user_id
        self.school_id = school_id
        self.username = username
        self.roles = roles

    @property
    def id(self) -> UUID:
        """Backward-compatible alias used by the Agent/Chat layers."""
        return self.user_id

    def has_role(self, role: str) -> bool:
        return role.upper() in {item.upper() for item in self.roles}


class AuthenticatedStudent:
    """认证学生"""
    def __init__(
        self,
        user_id: UUID,
        school_id: UUID,
        student_id: UUID,
        student_name: str,
        roles: list[str] | None = None,
    ):
        self.user_id = user_id
        self.school_id = school_id
        self.student_id = student_id
        self.student_name = student_name
        # Roles always come from the authenticated user's database relation;
        # an omitted value must never silently grant STUDENT access.
        self.roles = roles or []

    @property
    def id(self) -> UUID:
        """The chat layer historically used ``current_user.id``.

        Keep that access pattern stable while making the distinction between
        the authenticated user and the linked student explicit.
        """
        return self.user_id

    def has_role(self, role: str) -> bool:
        return role.upper() in {item.upper() for item in self.roles}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedUser:
    """获取当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    token = credentials.credentials
    payload = decode_token(token, expected_type="access")

    if not payload:
        raise credentials_exception

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception

    try:
        parsed_user_id = UUID(str(user_id))
    except (TypeError, ValueError):
        raise credentials_exception

    # 查询用户
    result = await db.execute(
        select(User).where(User.id == parsed_user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active"
        )

    # 角色必须从数据库读取，不能信任 JWT 中的可变 claims。
    role_result = await db.execute(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user.id,
            UserRole.school_id == user.school_id,
        )
    )
    roles = [code for code in role_result.scalars().all() if code]

    return AuthenticatedUser(
        user_id=user.id,
        school_id=user.school_id,
        username=user.username,
        roles=roles,
    )


async def get_current_student(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedStudent:
    """获取当前学生"""
    # 验证是否为学生角色
    if not current_user.has_role("STUDENT"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a student"
        )

    # 查询学生信息
    result = await db.execute(
        select(Student).where(
            Student.user_id == current_user.user_id,
            Student.school_id == current_user.school_id,
            Student.status == "active"
        )
    )
    student = result.scalar_one_or_none()

    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student profile not found"
        )

    return AuthenticatedStudent(
        user_id=current_user.user_id,
        school_id=student.school_id,
        student_id=student.id,
        student_name=student.name,
        roles=current_user.roles,
    )


async def require_admin(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Require a management role for Prompt/Trace administration."""
    allowed = {"SUPER_ADMIN", "SCHOOL_ADMIN", "CITY_OPERATOR", "QA"}
    if not allowed.intersection({role.upper() for role in current_user.roles}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有管理权限",
            headers={"X-Error-Code": "ADMIN_REQUIRED"},
        )
    return current_user


def require_management(*allowed_roles: str):
    """Create a dependency for teacher/school/city operations endpoints."""
    normalized = {role.upper() for role in allowed_roles}

    async def dependency(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if not normalized.intersection({role.upper() for role in current_user.roles}):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="没有访问该工作台的权限",
                headers={"X-Error-Code": "MANAGEMENT_ROLE_REQUIRED"},
            )
        return current_user

    return dependency
