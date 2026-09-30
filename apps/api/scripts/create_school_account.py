#!/usr/bin/env python3
"""Provision the first production account without fixtures or default passwords.

`seed_platform.py` and `init_test_data.py` intentionally refuse to run outside
development/test, so a deployed environment has no supported way to create its
first login. This script fills that gap: it creates the school and one account
with a strong password and prints the credentials once.

Usage (inside the api container):
    python scripts/create_school_account.py --school-code 441701001001 \
        --school-name 阳江一中 --username admin01 --role SCHOOL_ADMIN

Student accounts are deliberately not created here: only the roster import
flow creates a login together with its student record.
"""
from __future__ import annotations

import argparse
import asyncio
import secrets
import string
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import DEMO_USERNAMES, get_password_hash
from app.db.models.school import School
from app.db.models.user import Role, User, UserRole

# Mirrors the login gate so a provisioned account is never rejected later.
DEMO_SCHOOL_CODE = "demo_school"
DEFAULT_PASSWORD = "password123"
ROLES = {
    "SCHOOL_ADMIN": ("学校管理员", "general"),
    "SCHOOL_VIEWER": ("全校基础数据查看", "general"),
    "EXAM_ADMIN": ("考试管理员", "general"),
    "CITY_OPERATOR": ("市级运营", "general"),
    "QA": ("质量核查", "general"),
    "TEACHER": ("任课教师", "teacher"),
}
ALPHABET = string.ascii_letters + string.digits


def generate_password(length: int = 20) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


async def provision(
    db: AsyncSession,
    *,
    school_code: str,
    school_name: str = "",
    username: str,
    role_code: str,
    display_name: str = "",
    password: str = "",
    reset_password: bool = False,
    must_change_password: bool = False,
) -> dict:
    """Create or update one school-scoped account. Returns printable details."""
    if username.casefold() in DEMO_USERNAMES:
        raise ValueError(f"账号名 {username} 属于示例账号，生产环境登录会被拦截，请换一个。")
    if school_code.casefold() == DEMO_SCHOOL_CODE:
        raise ValueError("学校代码不能使用 demo_school，生产环境登录会被拦截。")
    if role_code not in ROLES:
        raise ValueError(f"不支持的角色 {role_code}；可用：{'、'.join(ROLES)}。")
    if password and password == DEFAULT_PASSWORD:
        raise ValueError("不能使用默认密码 password123，生产环境登录会被拦截。")

    role_name, account_type = ROLES[role_code]
    school = await db.scalar(select(School).where(School.code == school_code))
    if school is None:
        school = School(
            id=uuid4(),
            code=school_code,
            name=school_name or school_code,
            external_school_id=school_code,
            source_system="manual",
            status="active",
        )
        db.add(school)
        await db.flush()
        created_school = True
    else:
        created_school = False

    role = await db.scalar(select(Role).where(Role.code == role_code))
    if role is None:
        role = Role(id=uuid4(), code=role_code, name=role_name)
        db.add(role)
        await db.flush()

    user = await db.scalar(
        select(User).where(
            User.school_id == school.id,
            User.username == username,
            User.account_type == account_type,
        )
    )
    created_user = user is None
    issued_password = ""
    if created_user:
        issued_password = password or generate_password()
        user = User(
            id=uuid4(),
            school_id=school.id,
            username=username,
            account_type=account_type,
            password_hash=get_password_hash(issued_password),
            display_name=display_name or username,
            must_change_password=must_change_password,
            status="active",
        )
        db.add(user)
        await db.flush()
    elif reset_password:
        issued_password = password or generate_password()
        user.password_hash = get_password_hash(issued_password)
        user.must_change_password = must_change_password
        user.status = "active"

    relation = await db.scalar(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.role_id == role.id,
            UserRole.school_id == school.id,
        )
    )
    if relation is None:
        db.add(UserRole(user_id=user.id, role_id=role.id, school_id=school.id))

    await db.commit()
    return {
        "school_code": school.code,
        "school_name": school.name,
        "school_id": str(school.id),
        "created_school": created_school,
        "username": user.username,
        "display_name": user.display_name,
        "role": role_code,
        "created_user": created_user,
        "password": issued_password,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="创建生产环境的学校与登录账号（不含示例数据）。")
    parser.add_argument("--school-code", required=True, help="学校代码，例如 441701001001；不能是 demo_school")
    parser.add_argument("--school-name", default="", help="学校名称，仅在学校首次创建时写入")
    parser.add_argument("--username", required=True, help="登录账号")
    parser.add_argument("--role", required=True, choices=sorted(ROLES), help="账号角色")
    parser.add_argument("--display-name", default="", help="显示姓名，默认与账号相同")
    parser.add_argument("--password", default="", help="指定密码；省略则随机生成强密码")
    parser.add_argument("--reset-password", action="store_true", help="账号已存在时重置密码")
    parser.add_argument("--force-change-password", action="store_true", help="要求该账号首次登录后修改密码")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    engine = create_async_engine(settings.DATABASE_URL)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            result = await provision(
                db,
                school_code=args.school_code,
                school_name=args.school_name,
                username=args.username,
                role_code=args.role,
                display_name=args.display_name,
                password=args.password,
                reset_password=args.reset_password,
                must_change_password=args.force_change_password,
            )
    except ValueError as error:
        print(f"未创建：{error}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()

    print(f"学校：{result['school_name']}（{result['school_code']}）{'· 新建' if result['created_school'] else '· 已存在'}")
    print(f"账号：{result['username']} · {result['role']} · {result['display_name']} {'· 新建' if result['created_user'] else '· 已存在'}")
    if result["password"]:
        print(f"密码：{result['password']}")
        print("请只通过安全渠道转交，不要写入 Git、工单或聊天记录；本机不会保存该密码。")
    else:
        print("未改动密码；如需重置请加 --reset-password。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
