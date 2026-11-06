#!/usr/bin/env python3
"""Split the existing school login from platform governance without moving data.

Run against the backed-up deployment. The credential file is private and never
printed; it is written exclusively before the transaction is committed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.models import Role, School, Student, TeacherProfile, User, UserRole
from app.db.models.trace import AuditLog

OPERATION = "platform_admin_separation_20261106"


async def roles_for(db, user):
    return list((await db.scalars(select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(
        UserRole.user_id == user.id, UserRole.school_id == user.school_id))).all())


def record(db, actor, action, resource, school_id, details):
    db.add(AuditLog(actor_type="system", actor_id=actor.id, action="administrator." + action,
        resource_type=resource.__tablename__, resource_id=resource.id, allowed=True,
        extra_data={"school_id": str(school_id), "operation": OPERATION, **details}))


async def separate(db, *, credential_file: Path, expected_code: str, school_name: str,
                   school_code: str, phase: str, legacy_username="admin"):
    matches = (await db.scalars(select(User).where(User.username == legacy_username,
        User.account_type == "general", User.status == "active").with_for_update())).all()
    if len(matches) != 1:
        raise ValueError("原学校管理员账号不存在或重名，请先核对。")
    legacy = matches[0]
    school = await db.scalar(select(School).where(School.id == legacy.school_id).with_for_update())
    if not school or school.code not in {expected_code, school_code}:
        raise ValueError("学校编码与预期不一致，未进行修改。")
    if await db.scalar(select(School.id).where(School.code == school_code, School.id != school.id)):
        raise ValueError("目标学校编码已被其他学校使用。")
    for field in (TeacherProfile.fields, Student.profile_fields):
        table = field.class_
        pairs = (await db.execute(select(field["学校名称"].as_string(), field["学校编号"].as_string())
            .where(table.school_id == school.id).distinct())).all()
        if any((name and str(name).strip() != school_name) or (code and str(code).strip() != school_code) for name, code in pairs):
            raise ValueError("导入档案的学校名称或编码与目标不一致，未进行修改。")
    original_roles = await roles_for(db, legacy)
    if "SCHOOL_ADMIN" not in original_roles or set(original_roles) - {"SCHOOL_ADMIN", "SUPER_ADMIN"}:
        raise ValueError("原账号不是预期的学校管理员，请先核对其角色。")
    super_role = await db.scalar(select(Role).where(Role.code == "SUPER_ADMIN"))
    if not super_role:
        raise ValueError("缺少超级管理员角色。")

    existing = None
    if credential_file.exists():
        if credential_file.is_symlink():
            raise ValueError("凭据文件不能是符号链接。")
        saved = json.loads(credential_file.read_text())
        if saved.get("operation") != OPERATION or saved.get("legacy_user_id") != str(legacy.id):
            raise ValueError("已有凭据文件不属于本次操作。")
        existing = await db.get(User, UUID(saved["super_admin_id"]))
        if not existing or existing.status != "active" or await roles_for(db, existing) != ["SUPER_ADMIN"]:
            raise ValueError("已有独立超管账号与凭据记录不一致。")
    others = list((await db.scalars(select(User.id).join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.role_id == super_role.id, User.id != legacy.id, User.status == "active"))).all())
    if others and (not existing or set(others) != {existing.id}):
        raise ValueError("已存在其他独立超管账号，请先确认其身份，未创建新账号。")
    if phase == "finalize" and (not existing or not existing.last_login_at):
        raise ValueError("请先创建独立超管并验证登录，再撤销原账号的超管权限。")
    if not existing and "SUPER_ADMIN" not in original_roles:
        raise ValueError("原账号没有待分离的超管权限。")

    created_file = False
    try:
        platform = existing
        if platform is None:
            for _ in range(30):
                username = f"{secrets.randbelow(100_000_000):08d}"
                if not await db.scalar(select(User.id).where(User.username == username)):
                    break
            else:
                raise ValueError("暂时无法分配独立账号。")
            password = secrets.token_urlsafe(24)
            platform = User(id=uuid4(), school_id=school.id, username=username, administrator_code=username,
                account_type="general", display_name="平台超级管理员", status="active",
                password_hash=get_password_hash(password), must_change_password=False)
            db.add(platform)
            await db.flush()
            db.add(UserRole(user_id=platform.id, school_id=school.id, role_id=super_role.id))
            # This reference satisfies the existing identity schema. Access is
            # governed by SUPER_ADMIN's explicit governance-only API policy.
            record(db, legacy, "platform_account.create", platform, school.id,
                {"after": {"username": username, "roles": ["SUPER_ADMIN"]}})
            payload = {"operation": OPERATION, "legacy_user_id": str(legacy.id), "school_id": str(school.id),
                "super_admin_id": str(platform.id), "username": username, "initial_password": password,
                "must_change_password": True, "purpose": "仅管理员账号、权限与操作历史管理"}
            descriptor = os.open(credential_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created_file = True
            with os.fdopen(descriptor, "w") as output:
                json.dump(payload, output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())

        if phase == "finalize" and (school.name, school.code) != (school_name, school_code):
            before = {"school_name": school.name, "school_code": school.code}
            school.name, school.code = school_name, school_code
            record(db, platform, "school_identity.update", school, school.id,
                {"before": before, "after": {"school_name": school_name, "school_code": school_code}})
        if phase == "finalize" and "SUPER_ADMIN" in original_roles:
            await db.execute(delete(UserRole).where(UserRole.user_id == legacy.id, UserRole.role_id == super_role.id))
            legacy.password_version += 1
            record(db, platform, "platform_access.remove", legacy, school.id,
                {"before": {"roles": sorted(original_roles)}, "after": {"roles": ["SCHOOL_ADMIN"]}})
            platform.must_change_password = True
            platform.password_version += 1
        await db.flush()
        legacy_roles = sorted(await roles_for(db, legacy))
        if await roles_for(db, platform) != ["SUPER_ADMIN"] or (phase == "finalize" and legacy_roles != ["SCHOOL_ADMIN"]):
            raise ValueError("角色分离验证失败。")
        await db.commit()
        return {"school_id": str(school.id), "school_name": school.name, "school_code": school.code,
            "school_admin": legacy.username, "school_admin_roles": legacy_roles,
            "platform_admin": platform.username, "platform_admin_roles": ["SUPER_ADMIN"],
            "created_platform_account": created_file, "credential_file": str(credential_file)}
    except Exception:
        await db.rollback()
        if created_file:
            credential_file.unlink(missing_ok=True)
        raise


async def main(args):
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            result = await separate(db, credential_file=Path(args.credential_file), expected_code=args.expected_code,
                school_name=args.school_name, school_code=args.school_code, legacy_username=args.legacy_username, phase=args.phase)
            print(json.dumps(result, ensure_ascii=False))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credential-file", required=True)
    parser.add_argument("--expected-code", required=True)
    parser.add_argument("--school-name", required=True)
    parser.add_argument("--school-code", required=True)
    parser.add_argument("--legacy-username", default="admin")
    parser.add_argument("--phase", choices=("prepare", "finalize"), required=True)
    try:
        asyncio.run(main(parser.parse_args()))
    except Exception as exc:
        # Do not print database parameters or credentials from exception reprs.
        print(str(exc) if isinstance(exc, ValueError) else "操作失败，数据库事务已回滚：" + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
