#!/usr/bin/env python3
"""
Phase 1 测试数据初始化脚本
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
import uuid
from datetime import datetime, date
from decimal import Decimal

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.models import *


async def init_test_data():
    """初始化测试数据"""

    # 创建数据库引擎
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as session:
        print("🚀 开始初始化测试数据...")

        # 1. 创建测试学校
        print("\n📚 创建测试学校...")
        school = School(
            id=uuid.uuid4(),
            name="测试中学",
            code="TEST_SCHOOL_001",
            status="active"
        )
        session.add(school)
        await session.flush()
        print(f"✅ 学校创建成功: {school.name} (ID: {school.id})")

        # 2. 获取学生角色
        print("\n👥 获取学生角色...")
        result = await session.execute(
            select(Role).where(Role.code == "STUDENT")
        )
        student_role = result.scalar_one()
        print(f"✅ 学生角色: {student_role.name}")

        # 3. 创建测试用户（学生）
        print("\n👤 创建测试学生用户...")
        user = User(
            id=uuid.uuid4(),
            school_id=school.id,
            username="test_student",
            password_hash=get_password_hash("password123"),
            display_name="张三",
            status="active"
        )
        session.add(user)
        await session.flush()
        print(f"✅ 用户创建成功: {user.username}")

        # 4. 关联用户角色
        user_role = UserRole(
            user_id=user.id,
            role_id=student_role.id,
            school_id=school.id
        )
        session.add(user_role)

        # 5. 创建学生档案
        print("\n🎓 创建学生档案...")
        student = Student(
            id=uuid.uuid4(),
            school_id=school.id,
            user_id=user.id,
            student_no="2024001",
            name="张三",
            status="active"
        )
        session.add(student)
        await session.flush()
        print(f"✅ 学生档案创建成功: {student.name} (学号: {student.student_no})")

        # 6. 创建科目
        print("\n📖 创建科目...")
        subjects = []
        subject_data = [
            ("MATH", "数学"),
            ("CHINESE", "语文"),
            ("ENGLISH", "英语"),
            ("PHYSICS", "物理"),
            ("CHEMISTRY", "化学"),
        ]
        for code, name in subject_data:
            subject = Subject(
                id=uuid.uuid4(),
                school_id=school.id,
                code=code,
                name=name
            )
            session.add(subject)
            subjects.append((code, subject))
        await session.flush()
        print(f"✅ 创建了 {len(subjects)} 个科目")

        # 7. 创建测试考试
        print("\n📝 创建测试考试...")
        exam = Exam(
            id=uuid.uuid4(),
            school_id=school.id,
            name="2026年秋季期中考试",
            exam_type="midterm",
            academic_year="2026",
            term="fall",
            start_date=date(2026, 11, 15),
            end_date=date(2026, 11, 17),
            status="active"
        )
        session.add(exam)
        await session.flush()
        print(f"✅ 考试创建成功: {exam.name}")

        # 8. 创建考试总分
        print("\n📊 创建学生成绩...")
        exam_score = StudentExamScore(
            id=uuid.uuid4(),
            school_id=school.id,
            student_id=student.id,
            exam_id=exam.id,
            total_score=Decimal("635.5"),
            full_score=Decimal("750"),
            class_rank=12,
            grade_rank=45,
            class_student_count=50,
            grade_student_count=420
        )
        session.add(exam_score)
        print(f"✅ 总分: {exam_score.total_score}/{exam_score.full_score}, 班级排名: {exam_score.class_rank}")

        # 9. 创建科目成绩
        subject_scores_data = [
            ("MATH", 128, 150, 15, 52, 125.3, 120.8),
            ("CHINESE", 118, 150, 10, 38, 115.2, 112.5),
            ("ENGLISH", 132, 150, 8, 35, 128.5, 125.0),
            ("PHYSICS", 89, 100, 18, 55, 85.2, 82.3),
            ("CHEMISTRY", 92, 100, 12, 42, 88.6, 85.7),
        ]

        for code, score_val, full, class_r, grade_r, class_a, grade_a in subject_scores_data:
            subject = next(s for c, s in subjects if c == code)
            subject_score = StudentSubjectScore(
                id=uuid.uuid4(),
                school_id=school.id,
                student_id=student.id,
                exam_id=exam.id,
                subject_id=subject.id,
                score=Decimal(str(score_val)),
                full_score=Decimal(str(full)),
                class_rank=class_r,
                grade_rank=grade_r,
                class_avg=Decimal(str(class_a)),
                grade_avg=Decimal(str(grade_a))
            )
            session.add(subject_score)
        print(f"✅ 创建了 {len(subject_scores_data)} 个科目成绩")

        # 10. 创建小题得分（数学）
        print("\n📝 创建小题得分...")
        math_subject = next(s for c, s in subjects if c == "MATH")
        question_scores_data = [
            ("1", 5, 5, 0),
            ("2", 5, 5, 0),
            ("17", 2, 5, 3),  # 丢分题
            ("20", 3, 5, 2),  # 丢分题
            ("22", 1, 5, 4),  # 丢分题
        ]

        for q_no, score_val, full, lost in question_scores_data:
            question_score = QuestionScore(
                id=uuid.uuid4(),
                school_id=school.id,
                student_id=student.id,
                exam_id=exam.id,
                subject_id=math_subject.id,
                question_no=q_no,
                score=Decimal(str(score_val)),
                full_score=Decimal(str(full)),
                lost_score=Decimal(str(lost)),
                answer_status="correct" if lost == 0 else "wrong"
            )
            session.add(question_score)
        print(f"✅ 创建了 {len(question_scores_data)} 个小题得分")

        # 11. 提交所有更改
        print("\n💾 提交数据...")
        await session.commit()

        print("\n" + "="*50)
        print("✅ 测试数据初始化完成！")
        print("="*50)
        print(f"\n登录信息：")
        print(f"  用户名: test_student")
        print(f"  密码: password123")
        print(f"  学校: {school.name}")
        print(f"  学生: {student.name}")
        print(f"  学生ID: {student.id}")
        print(f"\n考试信息：")
        print(f"  考试名称: {exam.name}")
        print(f"  总分: {exam_score.total_score}/{exam_score.full_score}")
        print(f"  班级排名: {exam_score.class_rank}/{exam_score.class_student_count}")
        print(f"  年级排名: {exam_score.grade_rank}/{exam_score.grade_student_count}")
        print("\n" + "="*50)


if __name__ == "__main__":
    asyncio.run(init_test_data())
