"""
考试成绩Tool
"""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.tools.base import BaseTool, ToolContext, ToolResult, EvidenceRef
from app.db.models.exam import Exam
from app.db.models.score import StudentExamScore


class GetExamSummaryTool(BaseTool):
    """获取考试总结Tool"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    def name(self) -> str:
        return "get_exam_summary"

    @property
    def description(self) -> str:
        return """
获取学生某次考试的总体情况，包括总分和排名。
如果不指定exam_id，返回最近一次考试。
"""

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "exam_id": {
                    "type": "string",
                    "description": "考试ID，可选，不提供则返回最近一次"
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

        try:
            # 确定考试
            if exam_id_str:
                exam_id = UUID(exam_id_str)
                # 查询指定考试
                exam_result = await self.db.execute(
                    select(Exam).where(
                        Exam.id == exam_id,
                        Exam.school_id == tool_context.school_id
                    )
                )
                exam = exam_result.scalar_one_or_none()
            else:
                # 查询最近一次考试（基于学生的成绩）
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

                exam_result = await self.db.execute(
                    select(Exam).where(
                        Exam.id == score.exam_id,
                        Exam.school_id == tool_context.school_id,
                    )
                )
                exam = exam_result.scalar_one_or_none()

            if not exam:
                return ToolResult(
                    ok=False,
                    error_code="EXAM_NOT_FOUND",
                    error_message="考试不存在",
                    data={}
                )

            # 查询学生成绩
            score_result = await self.db.execute(
                select(StudentExamScore).where(
                    StudentExamScore.student_id == tool_context.student_id,
                    StudentExamScore.school_id == tool_context.school_id,
                    StudentExamScore.exam_id == exam.id
                )
            )
            score = score_result.scalar_one_or_none()

            if not score:
                return ToolResult(
                    ok=False,
                    error_code="SCORE_NOT_FOUND",
                    error_message="未找到成绩记录",
                    data={}
                )

            # 返回结果
            return ToolResult(
                ok=True,
                data={
                    "exam_name": exam.name,
                    "exam_date": exam.start_date.isoformat() if exam.start_date else None,
                    "total_score": float(score.total_score),
                    "full_score": float(score.full_score) if score.full_score else 150.0,
                    "class_rank": score.class_rank,
                    "grade_rank": score.grade_rank,
                    "class_student_count": score.class_student_count,
                    "grade_student_count": score.grade_student_count
                },
                evidence=[
                    EvidenceRef(
                        type="student_exam_score",
                        resource_id=str(score.id),
                        label=exam.name,
                        as_of=score.updated_at
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
