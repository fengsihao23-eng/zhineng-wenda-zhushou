#!/usr/bin/env python3
"""Seed role accounts and platform workflow fixtures for local acceptance runs."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.models.platform import HumanHandoff, KnowledgeDocument, ParentAuthorization, RiskEvent
from app.db.models.school import School
from app.db.models.student import Student
from app.db.models.user import Role, User, UserRole


async def ensure_role(db: AsyncSession, code: str, name: str) -> Role:
    role = await db.scalar(select(Role).where(Role.code == code))
    if role is None:
        role = Role(id=uuid4(), code=code, name=name)
        db.add(role)
        await db.flush()
    return role


async def ensure_user(db: AsyncSession, school: School, role: Role, username: str, display_name: str) -> User:
    user = await db.scalar(select(User).where(User.school_id == school.id, User.username == username))
    if user is None:
        user = User(id=uuid4(), school_id=school.id, username=username, password_hash=get_password_hash("password123"), display_name=display_name, status="active")
        db.add(user)
        await db.flush()
    relation = await db.scalar(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id, UserRole.school_id == school.id))
    if relation is None:
        db.add(UserRole(user_id=user.id, role_id=role.id, school_id=school.id))
    return user


async def seed() -> None:
    settings.require_demo_environment()
    engine = create_async_engine(settings.DATABASE_URL)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        school = await db.scalar(select(School).where(School.code == "DEMO_SCHOOL"))
        if school is None:
            raise RuntimeError("示例学校不存在，请先在隔离的 development/test 环境初始化示例数据")
        roles = {
            "TEACHER": await ensure_role(db, "TEACHER", "教师"),
            "SCHOOL_ADMIN": await ensure_role(db, "SCHOOL_ADMIN", "学校管理员"),
            "CITY_OPERATOR": await ensure_role(db, "CITY_OPERATOR", "市级运营"),
            "STUDENT": await ensure_role(db, "STUDENT", "学生"),
        }
        # Migrate the original fixture names so the documented accounts stay
        # valid across upgrades without duplicating the score rows.
        for legacy, canonical in (("student1", "student_basic"), ("student2", "student_diagnosis")):
            legacy_user = await db.scalar(select(User).where(User.school_id == school.id, User.username == legacy))
            canonical_user = await db.scalar(select(User).where(User.school_id == school.id, User.username == canonical))
            if legacy_user is not None and canonical_user is None:
                legacy_user.username = canonical
        await db.flush()
        teacher = await ensure_user(db, school, roles["TEACHER"], "teacher_demo", "王老师")
        await ensure_user(db, school, roles["SCHOOL_ADMIN"], "school_admin_demo", "学校管理员")
        await ensure_user(db, school, roles["CITY_OPERATOR"], "city_operator_demo", "市级运营")
        for username, display_name in (("student_basic", "张三"), ("student_diagnosis", "李四")):
            student_user = await ensure_user(db, school, roles["STUDENT"], username, display_name)
            linked_student = await db.scalar(select(Student).where(Student.user_id == student_user.id, Student.school_id == school.id))
            if linked_student is None:
                db.add(Student(id=uuid4(), school_id=school.id, user_id=student_user.id, student_no=f"PLATFORM-{username}", name=display_name, status="active"))
        await db.flush()
        students = (await db.execute(select(Student).where(Student.school_id == school.id).order_by(Student.created_at.asc()))).scalars().all()
        if not students:
            raise RuntimeError("示范学校没有学生数据")
        student = students[0]
        if not await db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.school_id == school.id)):
            db.add(KnowledgeDocument(
                school_id=school.id, title="函数定义域与值域复习要点", subject="数学", doc_type="校本讲义",
                content="函数定义域应先检查分母、根式和对数的限制条件，再结合题意取交集。",
                source_name="示范中学教研组", source_reference="数学组 2026 春季复习讲义，第 2 章",
                source_url="https://example.edu.cn/teaching/math/domain", tags=["函数", "高频错点"], created_by=teacher.id,
                status="published", published_at=datetime.now(timezone.utc), reviewed_by=teacher.id, reviewed_at=datetime.now(timezone.utc),
            ))
        if not await db.scalar(select(RiskEvent).where(RiskEvent.school_id == school.id)):
            db.add(RiskEvent(
                school_id=school.id, student_id=student.id, event_type="score_drop", severity="medium",
                title="数学连续两次低于班级均分", detail="系统根据最近两次考试的科目成绩生成待确认事件，请老师结合答卷核实。",
                source="score_monitor", status="open",
            ))
        if not await db.scalar(select(HumanHandoff).where(HumanHandoff.school_id == school.id)):
            db.add(HumanHandoff(
                school_id=school.id, student_id=student.id, reason="学生请求老师解释错题", priority="high",
                summary="学生希望获得人工讲解，请班主任或数学老师在 24 小时内跟进。", status="open",
            ))
        if not await db.scalar(select(ParentAuthorization).where(ParentAuthorization.school_id == school.id)):
            db.add(ParentAuthorization(
                school_id=school.id, student_id=student.id, parent_name="张女士", parent_phone="138****8001",
                share_code="DEMO2026", scopes=["dashboard", "diagnosis", "feedback"], status="active",
                expires_at=datetime.now(timezone.utc) + timedelta(days=180), granted_at=datetime.now(timezone.utc),
            ))
        await db.commit()
    await engine.dispose()
    print("Platform fixtures ready for development/test only; credentials are not logged.")


if __name__ == "__main__":
    asyncio.run(seed())
