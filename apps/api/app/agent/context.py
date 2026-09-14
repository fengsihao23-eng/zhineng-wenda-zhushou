"""
StudentContextBuilder - 动态加载学生上下文
"""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime
from typing import Optional

from app.db.models.student import Student
from app.db.models.exam import Exam
from app.db.models.score import StudentExamScore
from app.db.models.diagnosis import StudentEntitlement


class StudentContext:
    """学生上下文数据"""

    def __init__(
        self,
        student_id: UUID,
        school_id: UUID,
        student_name: str,
        grade_id: Optional[UUID] = None,
        class_id: Optional[UUID] = None,
        entitlement_level: str = "BASIC",
        recent_exams: list[dict] = None,
        latest_exam: Optional[dict] = None
    ):
        self.student_id = student_id
        self.school_id = school_id
        self.student_name = student_name
        self.grade_id = grade_id
        self.class_id = class_id
        self.entitlement_level = entitlement_level
        self.recent_exams = recent_exams or []
        self.latest_exam = latest_exam

    def to_prompt_context(self) -> str:
        """转换为Prompt上下文"""
        lines = [
            "# 学生信息",
            f"- 姓名: {self.student_name}",
            f"- 学生ID: {self.student_id}",
            f"- 权益等级: {self.entitlement_level}",
            ""
        ]

        if self.latest_exam:
            lines.extend([
                "# 最近一次考试",
                f"- 考试名称: {self.latest_exam.get('exam_name', '')}",
                f"- 考试日期: {self.latest_exam.get('exam_date', '')}",
                f"- 总分: {self.latest_exam.get('total_score', '')} / {self.latest_exam.get('full_score', '')}",
                f"- 班级排名: {self.latest_exam.get('class_rank', '')} / {self.latest_exam.get('class_student_count', '')}",
                f"- 年级排名: {self.latest_exam.get('grade_rank', '')} / {self.latest_exam.get('grade_student_count', '')}",
                ""
            ])

        if len(self.recent_exams) > 1:
            lines.append("# 历史考试记录")
            for exam in self.recent_exams[:5]:
                lines.append(f"- {exam.get('exam_name', '')} ({exam.get('exam_date', '')}): {exam.get('total_score', '')}分")
            lines.append("")

        return "\n".join(lines)


class StudentContextBuilder:
    """学生上下文构建器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_context(
        self,
        student_id: UUID,
        school_id: UUID
    ) -> StudentContext:
        """构建学生上下文"""

        # 1. 查询学生基本信息
        student_result = await self.db.execute(
            select(Student).where(
                Student.id == student_id,
                Student.school_id == school_id
            )
        )
        student = student_result.scalar_one_or_none()

        if not student:
            raise ValueError(f"Student not found: {student_id}")

        # 2. 查询权益等级
        entitlement_result = await self.db.execute(
            select(StudentEntitlement).where(
                and_(
                    StudentEntitlement.student_id == student_id,
                    StudentEntitlement.school_id == school_id,
                    StudentEntitlement.status == "active",
                    StudentEntitlement.starts_at <= datetime.now(),
                    (StudentEntitlement.expires_at.is_(None) |
                     (StudentEntitlement.expires_at >= datetime.now()))
                )
            ).limit(1)
        )
        entitlement = entitlement_result.scalar_one_or_none()
        entitlement_level = "BASIC"
        if entitlement and entitlement.product_code in {"DIAGNOSIS", "DIAGNOSIS_REPORT"}:
            entitlement_level = "DIAGNOSIS"

        # 3. 查询最近的考试成绩（最多5次）
        recent_scores_result = await self.db.execute(
            select(StudentExamScore, Exam).join(
                Exam,
                and_(
                    StudentExamScore.exam_id == Exam.id,
                    Exam.school_id == school_id,
                ),
            ).where(
                StudentExamScore.student_id == student_id,
                StudentExamScore.school_id == school_id
            )
            .order_by(Exam.start_date.desc())
            .limit(5)
        )
        recent_scores = recent_scores_result.all()

        # 4. 构造考试列表
        recent_exams = []
        latest_exam = None

        for idx, (score, exam) in enumerate(recent_scores):
            exam_data = {
                "exam_id": str(exam.id),
                "exam_name": exam.name,
                "exam_date": exam.start_date.isoformat() if exam.start_date else None,
                "total_score": float(score.total_score),
                "full_score": float(score.full_score) if score.full_score else 150.0,
                "class_rank": score.class_rank,
                "grade_rank": score.grade_rank,
                "class_student_count": score.class_student_count,
                "grade_student_count": score.grade_student_count
            }
            recent_exams.append(exam_data)

            if idx == 0:
                latest_exam = exam_data

        # 5. 返回上下文对象
        return StudentContext(
            student_id=student_id,
            school_id=school_id,
            student_name=student.name,
            grade_id=student.grade_id,
            class_id=student.class_id,
            entitlement_level=entitlement_level,
            recent_exams=recent_exams,
            latest_exam=latest_exam
        )
