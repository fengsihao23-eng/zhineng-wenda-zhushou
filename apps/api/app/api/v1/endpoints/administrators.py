"""Super-admin creation, authorization and lifecycle governance."""
from datetime import datetime, timezone
import secrets
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.errors import ApiError
from app.core.security import get_password_hash
from app.db.models.administrator import AdministratorInvitation
from app.db.models.school import School
from app.db.models.trace import AuditLog
from app.db.models.user import Role, User, UserRole
from app.services.administrator_audit import ADMIN_ROLES, event

router = APIRouter()
PREFIX = "/platform/administrators"


async def super_admin(current=Depends(get_current_user)):
    if not current.has_role("SUPER_ADMIN"):
        raise ApiError(403, "SUPER_ADMIN_REQUIRED", "只有超级管理员可以管理管理员及查看操作历史。")
    return current


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def trim_profile_fields(cls, value, info):
        return value.strip() if isinstance(value, str) and info.field_name not in {"password", "new_password"} else value


class AdministratorCreate(StrictInput):
    username: str = Field(default="", max_length=8, pattern=r"^(?:[0-9]{8})?$")
    display_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(default="", max_length=30)
    password: str = Field(min_length=1, max_length=4096)
    school_id: UUID
    roles: list[Literal["SCHOOL_ADMIN", "EXAM_ADMIN", "SCHOOL_VIEWER", "QA"]] = Field(min_length=1, max_length=1)
    must_change_password: bool = True


class AdministratorUpdate(StrictInput):
    display_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(default="", max_length=30)
    school_id: UUID
    roles: list[Literal["SCHOOL_ADMIN", "EXAM_ADMIN", "SCHOOL_VIEWER", "QA"]] = Field(min_length=1, max_length=1)
    status: Literal["active", "disabled"]
    expected_revision: int = Field(ge=0)


class PasswordReset(StrictInput):
    new_password: str = Field(min_length=1, max_length=4096)
    must_change_password: bool = True
    expected_revision: int = Field(ge=0)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value):
    return utc(value).isoformat() if value else None


def administrator_ids():
    role_ids = select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.code.in_(ADMIN_ROLES))
    return select(User.id).where(or_(User.administrator_code.is_not(None), User.id.in_(role_ids)))


def snapshot(user):
    return {"username": user.username, "display_name": user.display_name, "phone": user.phone, "status": user.status,
            "school_id": str(user.school_id) if user.school_id else None}


async def user_roles(db, user):
    return list((await db.scalars(select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(
        UserRole.user_id == user.id, UserRole.school_id == user.school_id,
    ))).all())


async def serialize_user(db, user, school):
    roles = await user_roles(db, user)
    return {"id": str(user.id), **snapshot(user), "school_name": school.name if school else None,
            "school_code": school.code if school else None, "roles": roles,
            "account_type": user.account_type, "platform_id": str(user.platform_id) if user.platform_id else None,
            "must_change_password": user.must_change_password,
            "revision": user.password_version,
            "administrator_code": user.administrator_code, "is_administrator": bool(user.administrator_code or ADMIN_ROLES.intersection(roles)),
            "created_at": iso(user.created_at), "updated_at": iso(user.updated_at), "last_login_at": iso(user.last_login_at)}


@router.get(PREFIX + "/schools")
async def schools(current=Depends(super_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(School).order_by(School.name, School.id))).all()
    return [{"id": str(row.id), "name": row.name, "code": row.code, "status": row.status} for row in rows]


@router.post(PREFIX + "/invitations")
async def invitations_closed(current=Depends(super_admin)):
    raise ApiError(410, "ADMIN_REGISTRATION_CLOSED", "注册密钥已停用，请直接新增学校管理员。")


@router.get(PREFIX + "/invitations")
async def invitations(page: int = Query(1, ge=1),
                      page_size: int = Query(20, ge=1, le=100), current=Depends(super_admin), db: AsyncSession = Depends(get_db)):
    query = select(AdministratorInvitation)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await db.scalars(query.order_by(AdministratorInvitation.created_at.desc(), AdministratorInvitation.id.desc())
                             .offset((page - 1) * page_size).limit(page_size))).all()
    now = datetime.now(timezone.utc)
    return {"total": total, "items": [{"id": str(row.id),
        "label": row.label, "status": "expired" if row.status == "active" and utc(row.expires_at) <= now else row.status,
        "expires_at": iso(row.expires_at), "created_at": iso(row.created_at), "used_at": iso(row.used_at),
        "used_by": str(row.used_by) if row.used_by else None} for row in rows]}


@router.post(PREFIX + "/invitations/{identifier}/revoke")
async def revoke_invitation(identifier: UUID, request: Request, current=Depends(super_admin), db: AsyncSession = Depends(get_db)):
    item = await db.scalar(select(AdministratorInvitation).where(AdministratorInvitation.id == identifier).with_for_update())
    if not item:
        raise ApiError(404, "INVITATION_NOT_FOUND", "注册密钥记录不存在。")
    # CAS also works with SQLite, which does not implement SELECT FOR UPDATE.
    result = await db.execute(update(AdministratorInvitation).where(AdministratorInvitation.id == identifier,
        AdministratorInvitation.status == "active").values(status="revoked", revoked_at=datetime.now(timezone.utc)))
    if result.rowcount != 1:
        raise ApiError(409, "INVITATION_NOT_ACTIVE", "密钥已使用或已撤销，请刷新列表。")
    event(db, request, current.user_id, "invitation.revoke", item, None)
    await db.commit()
    return {"status": "revoked"}


@router.post("/auth/register-administrator")
async def registration_closed():
    raise ApiError(410, "ADMIN_REGISTRATION_CLOSED", "学校管理员账号由超级管理员创建，请联系超级管理员。")


@router.post(PREFIX, status_code=201)
async def create_administrator(payload: AdministratorCreate, request: Request, response: Response,
                               current=Depends(super_admin), db: AsyncSession = Depends(get_db)):
    school = await db.scalar(select(School).where(School.id == payload.school_id, School.status == "active"))
    if not school:
        raise ApiError(404, "SCHOOL_NOT_AVAILABLE", "请选择有效的学校。")
    granted = list((await db.scalars(select(Role).where(Role.code.in_(payload.roles)))).all())
    if len(granted) != len(payload.roles):
        raise ApiError(503, "ADMIN_ROLE_NOT_CONFIGURED", "所选权限尚未初始化，请联系系统维护人员。")
    username = payload.username
    if username:
        if await db.scalar(select(User.id).where(User.username == username)):
            raise ApiError(409, "ADMIN_USERNAME_EXISTS", "该八位账号已被使用，请换一个或留空自动生成。")
    else:
        for _ in range(20):
            username = f"{secrets.randbelow(100_000_000):08d}"
            if not await db.scalar(select(User.id).where(User.username == username)):
                break
        else:
            raise ApiError(503, "ADMIN_CODE_UNAVAILABLE", "暂时无法生成账号，请稍后重试。")
    password_hash = await run_in_threadpool(get_password_hash, payload.password)
    try:
        user = User(id=uuid4(), school_id=school.id, username=username, administrator_code=username, display_name=payload.display_name,
            phone=payload.phone or None, account_type="general", password_hash=password_hash, status="active",
            must_change_password=payload.must_change_password)
        db.add(user)
        await db.flush()
        db.add_all(UserRole(user_id=user.id, school_id=school.id, role_id=role.id) for role in granted)
        event(db, request, current.user_id, "create", user, school.id,
              extra={"after": {**snapshot(user), "school_name": school.name, "roles": sorted(payload.roles)}})
        await db.flush()
        result = await serialize_user(db, user, school)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ApiError(409, "ADMIN_USERNAME_EXISTS", "该八位账号已被使用，请换一个或留空自动生成。")
    except Exception:
        await db.rollback()
        raise
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(PREFIX)
async def administrators(school_id: UUID | None = None, q: str = Query("", max_length=100),
                         scope: Literal["administrators", "all"] = "administrators", status: str | None = None,
                         page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                         current=Depends(super_admin), db: AsyncSession = Depends(get_db)):
    query = select(User, School).outerjoin(School, School.id == User.school_id)
    if scope == "administrators":
        query = query.where(User.id.in_(administrator_ids()))
    if status:
        query = query.where(User.status == status)
    if school_id:
        query = query.where(User.school_id == school_id)
    if q.strip():
        query = query.where(or_(User.username.contains(q.strip(), autoescape=True), User.display_name.contains(q.strip(), autoescape=True)))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await db.execute(query.order_by(User.created_at.desc(), User.id.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return {"total": total, "items": [await serialize_user(db, user, school) for user, school in rows]}


@router.patch(PREFIX + "/{identifier}")
async def edit_administrator(identifier: UUID, payload: AdministratorUpdate, request: Request,
                             current=Depends(super_admin), db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.id == identifier, User.id.in_(administrator_ids()))
                           .with_for_update().execution_options(populate_existing=True))
    if not user:
        raise ApiError(404, "ADMIN_NOT_FOUND", "管理员不存在。")
    roles = await user_roles(db, user)
    if "SUPER_ADMIN" in roles:
        raise ApiError(403, "SUPER_ADMIN_PROTECTED", "超级管理员账号不能在此修改或禁用。")
    if user.status == "deleted":
        raise ApiError(409, "ADMIN_DELETED", "已删除的历史账号不能重新启用。")
    original_school = await db.get(School, user.school_id) if user.school_id else None
    before = {**snapshot(user), "school_name": original_school.name if original_school else None, "roles": sorted(roles)}
    school = await db.scalar(select(School).where(School.id == payload.school_id, School.status == "active"))
    if not school:
        raise ApiError(404, "SCHOOL_NOT_AVAILABLE", "请选择有效的学校。")
    granted = list((await db.scalars(select(Role).where(Role.code.in_(payload.roles)))).all())
    if len(granted) != len(payload.roles):
        raise ApiError(503, "ADMIN_ROLE_NOT_CONFIGURED", "所选权限尚未初始化，请联系系统维护人员。")
    # Existing teacher/student relations must not be rewritten by admin governance.
    other_roles = set(roles) - ADMIN_ROLES
    if other_roles and (user.school_id != school.id or set(payload.roles) != set(roles).intersection(ADMIN_ROLES)):
        raise ApiError(409, "ACCOUNT_HAS_OTHER_IDENTITIES", "该账号关联其他业务身份，请通过对应档案管理权限和学校。")
    after = {**snapshot(user), "display_name": payload.display_name, "phone": payload.phone or None,
             "status": payload.status, "school_id": str(school.id), "school_name": school.name,
             "roles": sorted(set(payload.roles) | other_roles)}
    if user.password_version != payload.expected_revision:
        raise ApiError(409, "ADMIN_VERSION_CONFLICT", "管理员信息已变化，请刷新后重新编辑。")
    changed = before != after
    if changed:
        values = {"display_name": payload.display_name, "phone": payload.phone or None, "status": payload.status,
                  "school_id": school.id, "updated_at": datetime.now(timezone.utc), "password_version": User.password_version + 1}
        try:
            await db.execute(delete(UserRole).where(UserRole.user_id == user.id))
            result = await db.execute(update(User).where(User.id == user.id, User.password_version == payload.expected_revision).values(**values))
            if result.rowcount != 1:
                raise ApiError(409, "ADMIN_VERSION_CONFLICT", "管理员信息已变化，请刷新后重新编辑。")
            other = list((await db.scalars(select(Role).where(Role.code.in_(other_roles)))).all())
            db.add_all(UserRole(user_id=user.id, school_id=school.id, role_id=role.id) for role in granted + other)
            await db.refresh(user)
            event(db, request, current.user_id, "update", user, user.school_id, extra={"before": before, "after": after})
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise ApiError(409, "ADMIN_SCHOOL_HAS_HISTORY", "该账号已关联原学校业务记录，不能迁移历史归属；请禁用旧账号并为新学校创建账号。")
        except Exception:
            await db.rollback()
            raise
    return await serialize_user(db, user, school)


@router.post(PREFIX + "/{identifier}/reset-password")
async def reset_password(identifier: UUID, payload: PasswordReset, request: Request,
                         current=Depends(super_admin), db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.id == identifier).with_for_update().execution_options(populate_existing=True))
    if not user:
        raise ApiError(404, "ACCOUNT_NOT_FOUND", "账号不存在。")
    if "SUPER_ADMIN" in await user_roles(db, user):
        raise ApiError(403, "SUPER_ADMIN_PROTECTED", "超级管理员请通过修改密码页面修改自己的密码。")
    if user.status == "deleted":
        raise ApiError(409, "ACCOUNT_DELETED", "已删除账号不能重置密码。")
    if user.password_version != payload.expected_revision:
        raise ApiError(409, "ADMIN_VERSION_CONFLICT", "账号信息已变化，请刷新后重试。")
    password_hash = await run_in_threadpool(get_password_hash, payload.new_password)
    changed = await db.execute(update(User).where(User.id == user.id, User.password_version == payload.expected_revision).values(
        password_hash=password_hash, password_version=User.password_version + 1,
        must_change_password=payload.must_change_password, updated_at=datetime.now(timezone.utc)))
    if changed.rowcount != 1:
        raise ApiError(409, "ADMIN_VERSION_CONFLICT", "账号信息已变化，请刷新后重试。")
    event(db, request, current.user_id, "password.reset", user, user.school_id,
          extra={"username": user.username, "must_change_password": payload.must_change_password})
    await db.commit()
    return {"id": str(user.id), "message": "密码已重置，原登录凭据已失效。"}


@router.get(PREFIX + "/history")
async def history(administrator_id: UUID | None = None, school_id: UUID | None = None,
                  action: str = Query("", max_length=100), allowed: bool | None = None,
                  since: datetime | None = None, until: datetime | None = None,
                  page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                  current=Depends(super_admin), db: AsyncSession = Depends(get_db)):
    if since and until and utc(since) > utc(until):
        raise ApiError(422, "INVALID_DATE_RANGE", "开始时间不能晚于结束时间。")
    query = select(AuditLog, User).outerjoin(User, User.id == AuditLog.actor_id)
    if not administrator_id:
        query = query.where(or_(AuditLog.action.startswith("administrator."), AuditLog.actor_id.in_(administrator_ids()),
            and_(AuditLog.resource_type == "users", AuditLog.resource_id.in_(administrator_ids()))))
    if administrator_id:
        query = query.where(or_(AuditLog.actor_id == administrator_id,
            and_(AuditLog.resource_type == "users", AuditLog.resource_id == administrator_id)))
    if school_id:
        # Use the recorded resource school before the actor's school (a super-admin can act across schools).
        recorded_school = AuditLog.extra_data["school_id"].as_string()
        query = query.where(or_(recorded_school == str(school_id), and_(recorded_school.is_(None), User.school_id == school_id)))
    if action:
        query = query.where(AuditLog.action.contains(action, autoescape=True))
    if allowed is not None:
        query = query.where(AuditLog.allowed == allowed)
    if since:
        query = query.where(AuditLog.created_at >= utc(since).replace(tzinfo=None))
    if until:
        query = query.where(AuditLog.created_at <= utc(until).replace(tzinfo=None))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await db.execute(query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    schools_by_id = {str(row.id): row.name for row in (await db.scalars(select(School))).all()}
    school_codes = {str(row.id): row.code for row in (await db.scalars(select(School))).all()}
    return {"total": total, "items": [{"id": str(row.id), "action": row.action, "actor_id": str(row.actor_id),
        "actor_name": "系统迁移" if row.actor_type == "system" else (user.display_name or user.username if user else "历史账号"), "actor_username": user.username if user else None,
        "school_name": schools_by_id.get((row.extra_data or {}).get("school_id") or (str(user.school_id) if user else "")),
        "school_code": school_codes.get((row.extra_data or {}).get("school_id") or (str(user.school_id) if user else "")),
        "resource_type": row.resource_type, "resource_id": str(row.resource_id) if row.resource_id else None,
        "allowed": row.allowed, "reason": row.reason, "details": row.extra_data or {},
        "ip_address": str(row.ip_address) if row.ip_address else None, "request_id": row.request_id,
        "created_at": iso(row.created_at)} for row, user in rows]}
