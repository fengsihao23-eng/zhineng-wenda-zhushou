"""
初始化测试数据

创建：
- 1个学校
- 2个用户（学生）
- 2个学生档案
- 5个科目
- 2次考试
- 完整成绩数据
- 1份诊断报告
- 权益数据
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from datetime import datetime, timedelta, date
from decimal import Decimal
import uuid

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.models.school import School
from app.db.models.user import User, Role, UserRole
from app.db.models.student import Student
from app.db.models.exam import Exam, Subject, ExamSubject
from app.db.models.score import StudentExamScore, StudentSubjectScore, QuestionScore
from app.db.models.diagnosis import DiagnosisReport, StudentEntitlement


async def init_test_data():
    """初始化测试数据"""

    settings.require_demo_environment()

    # 创建数据库引擎
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            # 1. 创建学校
            print("Creating school...")
            existing_school = await session.execute(
                select(School).where(School.code == "DEMO_SCHOOL")
            )
            school = existing_school.scalar_one_or_none()
            if school is not None:
                print(
                    f"Seed data already exists for {school.code} ({school.id}); "
                    "nothing to do."
                )
                return
            school = School(
                id=uuid.uuid4(),
                name="示范中学",
                code="DEMO_SCHOOL",
                status="active"
            )
            session.add(school)
            await session.flush()
            print(f"School created: {school.id}")

            # 2. 获取或创建角色
            print("Getting or creating roles...")
            roles = []
            for code, name in [
                ("STUDENT", "学生"),
                ("TEACHER", "教师"),
                ("SCHOOL_ADMIN", "学校管理员")
            ]:
                # 检查角色是否已存在
                result = await session.execute(
                    select(Role).where(Role.code == code)
                )
                role = result.scalar_one_or_none()
                if not role:
                    role = Role(code=code, name=name)
                    session.add(role)
                roles.append(role)
            await session.flush()
            print(f"Roles ready: {len(roles)}")

            # 3. 创建用户
            print("Creating users...")
            users_data = [
                {
                    "username": "student_basic",
                    "password": "password123",
                    "display_name": "张三",
                    "role": "STUDENT"
                },
                {
                    "username": "student_diagnosis",
                    "password": "password123",
                    "display_name": "李四",
                    "role": "STUDENT"
                }
            ]

            users = []
            for user_data in users_data:
                user = User(
                    id=uuid.uuid4(),
                    school_id=school.id,
                    username=user_data["username"],
                    password_hash=get_password_hash(user_data["password"]),
                    display_name=user_data["display_name"],
                    status="active"
                )
                users.append(user)
                session.add(user)
            await session.flush()
            print(f"Users created: {len(users)}")

            # 4. 分配角色
            print("Assigning roles...")
            student_role = next(r for r in roles if r.code == "STUDENT")
            for user in users:
                user_role = UserRole(
                    user_id=user.id,
                    role_id=student_role.id,
                    school_id=school.id
                )
                session.add(user_role)
            await session.flush()

            # 5. 创建学生档案
            print("Creating students...")
            students = []
            for idx, user in enumerate(users):
                student = Student(
                    id=uuid.uuid4(),
                    school_id=school.id,
                    user_id=user.id,
                    student_no=f"2024{idx+1:04d}",
                    name=user.display_name,
                    status="active"
                )
                students.append(student)
                session.add(student)
            await session.flush()
            print(f"Students created: {len(students)}")

            # 6. 创建科目
            print("Creating subjects...")
            subjects_data = [
                ("MATH", "数学"),
                ("CHINESE", "语文"),
                ("ENGLISH", "英语"),
                ("PHYSICS", "物理"),
                ("CHEMISTRY", "化学")
            ]

            subjects = []
            for code, name in subjects_data:
                subject = Subject(
                    id=uuid.uuid4(),
                    school_id=school.id,
                    code=code,
                    name=name
                )
                subjects.append(subject)
                session.add(subject)
            await session.flush()
            print(f"Subjects created: {len(subjects)}")

            # 7. 创建考试
            print("Creating exams...")
            exams = []
            for idx in range(2):
                exam = Exam(
                    id=uuid.uuid4(),
                    school_id=school.id,
                    name=f"2024学年第{idx+1}次月考",
                    exam_type="monthly",
                    academic_year="2024",
                    term="spring",
                    start_date=date.today() - timedelta(days=30 * (2-idx)),
                    status="active"
                )
                exams.append(exam)
                session.add(exam)
            await session.flush()
            print(f"Exams created: {len(exams)}")

            # 8. 创建考试科目
            print("Creating exam subjects...")
            for exam in exams:
                for subject in subjects:
                    exam_subject = ExamSubject(
                        id=uuid.uuid4(),
                        exam_id=exam.id,
                        subject_id=subject.id,
                        full_score=Decimal("150.0"),
                        grade_avg=Decimal("95.0"),
                        class_avg=Decimal("92.0")
                    )
                    session.add(exam_subject)
            await session.flush()

            # 9. 创建成绩数据
            print("Creating scores...")

            # 学生1: BASIC用户, 成绩中等偏上
            student1 = students[0]
            exam1_scores = [
                ("MATH", 128.5),
                ("CHINESE", 112.0),
                ("ENGLISH", 135.0),
                ("PHYSICS", 98.0),
                ("CHEMISTRY", 105.5)
            ]
            exam2_scores = [
                ("MATH", 135.0),
                ("CHINESE", 118.0),
                ("ENGLISH", 138.0),
                ("PHYSICS", 102.0),
                ("CHEMISTRY", 110.0)
            ]

            # 学生2: DIAGNOSIS用户, 成绩优秀
            student2 = students[1]
            exam1_scores_s2 = [
                ("MATH", 142.0),
                ("CHINESE", 125.0),
                ("ENGLISH", 145.0),
                ("PHYSICS", 115.0),
                ("CHEMISTRY", 120.0)
            ]
            exam2_scores_s2 = [
                ("MATH", 145.0),
                ("CHINESE", 128.0),
                ("ENGLISH", 148.0),
                ("PHYSICS", 118.0),
                ("CHEMISTRY", 125.0)
            ]

            # 生成成绩
            for student, exam, scores_data in [
                (student1, exams[0], exam1_scores),
                (student1, exams[1], exam2_scores),
                (student2, exams[0], exam1_scores_s2),
                (student2, exams[1], exam2_scores_s2)
            ]:
                # 总分
                total_score = sum(score for _, score in scores_data)
                exam_score = StudentExamScore(
                    id=uuid.uuid4(),
                    school_id=school.id,
                    student_id=student.id,
                    exam_id=exam.id,
                    total_score=Decimal(str(total_score)),
                    full_score=Decimal("750.0"),
                    class_rank=15 if student == student1 else 3,
                    grade_rank=31 if student == student1 else 8,
                    class_student_count=50,
                    grade_student_count=420
                )
                session.add(exam_score)

                # 科目成绩
                for subject_code, score in scores_data:
                    subject = next(s for s in subjects if s.code == subject_code)
                    subject_score = StudentSubjectScore(
                        id=uuid.uuid4(),
                        school_id=school.id,
                        student_id=student.id,
                        exam_id=exam.id,
                        subject_id=subject.id,
                        score=Decimal(str(score)),
                        full_score=Decimal("150.0"),
                        class_rank=12 if student == student1 else 2,
                        grade_rank=28 if student == student1 else 5,
                        class_avg=Decimal("92.0"),
                        grade_avg=Decimal("95.0")
                    )
                    session.add(subject_score)

                    # 小题得分（每科5题）
                    for q_no in range(1, 6):
                        full = 30.0
                        lost = 5.0 if q_no == 3 else 2.0
                        question_score = QuestionScore(
                            id=uuid.uuid4(),
                            school_id=school.id,
                            student_id=student.id,
                            exam_id=exam.id,
                            subject_id=subject.id,
                            question_no=str(q_no),
                            score=Decimal(str(full - lost)),
                            full_score=Decimal(str(full)),
                            lost_score=Decimal(str(lost)),
                            answer_status="correct" if lost == 0 else "partial"
                        )
                        session.add(question_score)

            await session.flush()
            print("Scores created")

            # 10. 创建诊断报告（仅学生2）
            print("Creating diagnosis report...")
            diagnosis = DiagnosisReport(
                id=uuid.uuid4(),
                school_id=school.id,
                student_id=students[1].id,
                exam_id=exams[0].id,
                report_type="exam",
                status="generated",
                structured_json={
                    "summary": "整体表现优秀，数学有提升空间",
                    "knowledge_gaps": ["函数定义域", "立体几何"],
                    "recommendations": ["加强函数综合题练习", "提高空间想象能力"],
                    "strengths": ["英语阅读理解", "化学实验题"],
                    "areas_for_improvement": ["数学应用题", "物理力学"]
                },
                generated_at=datetime.utcnow()
            )
            session.add(diagnosis)
            await session.flush()

            # 11. 创建权益数据
            print("Creating entitlements...")

            # 学生1: 仅BASIC
            # 学生2: DIAGNOSIS
            entitlement = StudentEntitlement(
                id=uuid.uuid4(),
                school_id=school.id,
                student_id=students[1].id,
                product_code="DIAGNOSIS",
                resource_type="exam",
                resource_id=exams[0].id,
                status="active",
                starts_at=datetime.utcnow() - timedelta(days=30),
                expires_at=datetime.utcnow() + timedelta(days=335)
            )
            session.add(entitlement)

            await session.commit()

            print("\n" + "="*60)
            print("✅ 测试数据初始化完成！")
            print("="*60)
            print(f"\n学校: {school.name} (ID: {school.id})")
            print(f"\n测试账号:")
            print("  1. BASIC 示例账号已创建")
            print("  2. DIAGNOSIS 示例账号已创建")
            print("  凭据不输出到日志；仅用于隔离的 development/test 环境。")
            print(f"\n考试: {len(exams)}次")
            print(f"科目: {len(subjects)}门")
            print(f"成绩数据: 已生成")
            print(f"诊断报告: 1份 (student_diagnosis)")
            print("\n" + "="*60)

        except Exception as e:
            print(f"Error: {e}")
            await session.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(init_test_data())
