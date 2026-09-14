"""
成绩相关Tool集合
"""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional

from app.tools.base import BaseTool, ToolContext, ToolResult, EvidenceRef
from app.db.models.exam import Exam, Subject
from app.db.models.score import StudentSubjectScore, StudentExamScore, QuestionScore


class GetSubjectScoresTool(BaseTool):
    """获取科目成绩Tool"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    def name(self) -> str:
        return "get_subject_scores"

    @property
    def description(self) -> str:
        return """
获取学生某次考试的各科成绩详情，包括得分、排名、平均分对比。
如果不指定exam_id，返回最近一次考试的科目成绩。
"""

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "exam_id": {
                    "type": "string",
                    "description": "考试ID，可选，不提供则返回最近一次"
                },
                "subject_name": {
                    "type": "string",
                    "description": "科目名称，可选，用于筛选特定科目"
                }
            }
        }

    async def execute(
        self,
        tool_context: ToolContext,
        args: dict
    ) -> ToolResult:
        """执行Tool"""
        exam_id_str = args.get("exam_id")
        subject_name = args.get("subject_name")

        try:
            # 确定考试ID
            if exam_id_str:
                exam_id = UUID(exam_id_str)
            else:
                # 获取最近一次考试
                score_result = await self.db.execute(
                    select(StudentExamScore)
                    .where(
                        StudentExamScore.student_id == tool_context.student_id,
                        StudentExamScore.school_id == tool_context.school_id
                    )
                    .order_by(StudentExamScore.created_at.desc())
                    .limit(1)
                )
                score = score_result.scalar_one_or_none()
                if not score:
                    return ToolResult(
                        ok=False,
                        error_code="NO_EXAM_FOUND",
                        error_message="未找到考试记录",
                        data={}
                    )
                exam_id = score.exam_id

            # 查询科目成绩
            query = select(StudentSubjectScore, Subject).join(
                Subject,
                and_(
                    StudentSubjectScore.subject_id == Subject.id,
                    Subject.school_id == tool_context.school_id,
                ),
            ).where(
                and_(
                    StudentSubjectScore.student_id == tool_context.student_id,
                    StudentSubjectScore.exam_id == exam_id,
                    StudentSubjectScore.school_id == tool_context.school_id
                )
            )

            if subject_name:
                query = query.where(Subject.name.ilike(f"%{subject_name}%"))

            result = await self.db.execute(query)
            rows = result.all()

            if not rows:
                return ToolResult(
                    ok=False,
                    error_code="NO_SUBJECT_SCORES_FOUND",
                    error_message="未找到科目成绩",
                    data={}
                )

            # 构造返回数据
            subjects = []
            evidence = []
            for score, subject in rows:
                subjects.append({
                    "subject_name": subject.name,
                    "score": float(score.score),
                    "full_score": float(score.full_score),
                    "score_rate": round(float(score.score) / float(score.full_score) * 100, 2),
                    "class_rank": score.class_rank,
                    "grade_rank": score.grade_rank,
                    "class_avg": float(score.class_avg) if score.class_avg else None,
                    "grade_avg": float(score.grade_avg) if score.grade_avg else None,
                    "vs_class_avg": round(float(score.score) - float(score.class_avg), 2) if score.class_avg else None,
                    "vs_grade_avg": round(float(score.score) - float(score.grade_avg), 2) if score.grade_avg else None
                })
                evidence.append(
                    EvidenceRef(
                        type="student_subject_score",
                        resource_id=str(score.id),
                        label=f"{subject.name}成绩",
                        as_of=score.updated_at
                    )
                )

            return ToolResult(
                ok=True,
                data={
                    "exam_id": str(exam_id),
                    "subject_count": len(subjects),
                    "subjects": subjects
                },
                evidence=evidence
            )

        except Exception as e:
            return ToolResult(
                ok=False,
                error_code="TOOL_EXECUTION_ERROR",
                error_message="数据查询失败，请稍后重试",
                data={}
            )


class GetRankingChangeTool(BaseTool):
    """获取排名变化Tool"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    def name(self) -> str:
        return "get_rank_change"

    @property
    def description(self) -> str:
        return """
对比两次考试的排名变化，包括总分排名和各科排名的变化。
如果不指定两次考试ID，则对比最近两次考试。
"""

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "current_exam_id": {
                    "type": "string",
                    "description": "当前考试ID，可选"
                },
                "previous_exam_id": {
                    "type": "string",
                    "description": "对比考试ID，可选"
                }
            }
        }

    async def execute(
        self,
        tool_context: ToolContext,
        args: dict
    ) -> ToolResult:
        """执行Tool"""
        current_exam_id_str = args.get("current_exam_id")
        previous_exam_id_str = args.get("previous_exam_id")

        try:
            # 确定两次考试ID
            if current_exam_id_str and previous_exam_id_str:
                current_exam_id = UUID(current_exam_id_str)
                previous_exam_id = UUID(previous_exam_id_str)
            else:
                # 获取最近两次考试
                scores_result = await self.db.execute(
                    select(StudentExamScore)
                    .where(
                        StudentExamScore.student_id == tool_context.student_id,
                        StudentExamScore.school_id == tool_context.school_id
                    )
                    .order_by(StudentExamScore.created_at.desc())
                    .limit(2)
                )
                scores = scores_result.scalars().all()
                if len(scores) < 2:
                    return ToolResult(
                        ok=False,
                        error_code="INSUFFICIENT_EXAMS",
                        error_message="需要至少两次考试记录才能对比",
                        data={}
                    )
                current_exam_id = scores[0].exam_id
                previous_exam_id = scores[1].exam_id

            # 查询两次考试的总分成绩
            current_score_result = await self.db.execute(
                select(StudentExamScore).where(
                    StudentExamScore.student_id == tool_context.student_id,
                    StudentExamScore.school_id == tool_context.school_id,
                    StudentExamScore.exam_id == current_exam_id
                )
            )
            current_score = current_score_result.scalar_one_or_none()

            previous_score_result = await self.db.execute(
                select(StudentExamScore).where(
                    StudentExamScore.student_id == tool_context.student_id,
                    StudentExamScore.school_id == tool_context.school_id,
                    StudentExamScore.exam_id == previous_exam_id
                )
            )
            previous_score = previous_score_result.scalar_one_or_none()

            if not current_score or not previous_score:
                return ToolResult(
                    ok=False,
                    error_code="SCORE_NOT_FOUND",
                    error_message="未找到完整的成绩记录",
                    data={}
                )

            # 计算总分排名变化
            total_score_change = {
                "current_total_score": float(current_score.total_score),
                "previous_total_score": float(previous_score.total_score),
                "score_change": round(float(current_score.total_score) - float(previous_score.total_score), 2),
                "current_class_rank": current_score.class_rank,
                "previous_class_rank": previous_score.class_rank,
                "class_rank_change": previous_score.class_rank - current_score.class_rank if (current_score.class_rank and previous_score.class_rank) else None,
                "current_grade_rank": current_score.grade_rank,
                "previous_grade_rank": previous_score.grade_rank,
                "grade_rank_change": previous_score.grade_rank - current_score.grade_rank if (current_score.grade_rank and previous_score.grade_rank) else None
            }

            # 查询各科排名变化
            current_subjects_result = await self.db.execute(
                select(StudentSubjectScore, Subject).join(
                    Subject,
                    and_(
                        StudentSubjectScore.subject_id == Subject.id,
                        Subject.school_id == tool_context.school_id,
                    ),
                ).where(
                    StudentSubjectScore.student_id == tool_context.student_id,
                    StudentSubjectScore.school_id == tool_context.school_id,
                    StudentSubjectScore.exam_id == current_exam_id
                )
            )
            current_subjects = {subject.name: score for score, subject in current_subjects_result.all()}

            previous_subjects_result = await self.db.execute(
                select(StudentSubjectScore, Subject).join(
                    Subject,
                    and_(
                        StudentSubjectScore.subject_id == Subject.id,
                        Subject.school_id == tool_context.school_id,
                    ),
                ).where(
                    StudentSubjectScore.student_id == tool_context.student_id,
                    StudentSubjectScore.school_id == tool_context.school_id,
                    StudentSubjectScore.exam_id == previous_exam_id
                )
            )
            previous_subjects = {subject.name: score for score, subject in previous_subjects_result.all()}

            # 对比各科
            subject_changes = []
            for subject_name in current_subjects.keys():
                if subject_name in previous_subjects:
                    curr = current_subjects[subject_name]
                    prev = previous_subjects[subject_name]
                    subject_changes.append({
                        "subject_name": subject_name,
                        "current_score": float(curr.score),
                        "previous_score": float(prev.score),
                        "score_change": round(float(curr.score) - float(prev.score), 2),
                        "current_rank": curr.class_rank,
                        "previous_rank": prev.class_rank,
                        "rank_change": prev.class_rank - curr.class_rank if (curr.class_rank and prev.class_rank) else None
                    })

            return ToolResult(
                ok=True,
                data={
                    "current_exam_id": str(current_exam_id),
                    "previous_exam_id": str(previous_exam_id),
                    "total_score_change": total_score_change,
                    "subject_changes": subject_changes
                },
                evidence=[
                    EvidenceRef(
                        type="student_exam_score",
                        resource_id=str(current_score.id),
                        label="当前考试成绩",
                        as_of=current_score.updated_at
                    ),
                    EvidenceRef(
                        type="student_exam_score",
                        resource_id=str(previous_score.id),
                        label="上次考试成绩",
                        as_of=previous_score.updated_at
                    )
                ]
            )

        except Exception as e:
            return ToolResult(
                ok=False,
                error_code="TOOL_EXECUTION_ERROR",
                error_message="数据查询失败，请稍后重试",
                data={}
            )
