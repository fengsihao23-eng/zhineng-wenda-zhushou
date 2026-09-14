"""
分析类Tool集合
"""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import Optional

from app.tools.base import BaseTool, ToolContext, ToolResult, EvidenceRef
from app.db.models.exam import Exam, Subject
from app.db.models.score import StudentExamScore, QuestionScore
from app.db.models.diagnosis import DiagnosisReport


class GetScoreTrendTool(BaseTool):
    """获取成绩趋势Tool"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    def name(self) -> str:
        return "get_score_trend"

    @property
    def description(self) -> str:
        return """
获取学生最近N次考试的成绩趋势，包括总分趋势和各科趋势。
默认返回最近5次考试的趋势数据。
"""

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "返回最近N次考试，默认5次",
                    "default": 5
                },
                "subject_name": {
                    "type": "string",
                    "description": "科目名称，可选，用于查看特定科目趋势"
                }
            }
        }

    async def execute(
        self,
        tool_context: ToolContext,
        args: dict
    ) -> ToolResult:
        """执行Tool"""
        limit = min(max(int(args.get("limit", 5)), 1), 20)
        subject_name = args.get("subject_name")

        try:
            # 查询最近N次考试的总分
            scores_result = await self.db.execute(
                select(StudentExamScore, Exam).join(
                    Exam,
                    and_(
                        StudentExamScore.exam_id == Exam.id,
                        Exam.school_id == tool_context.school_id,
                    ),
                ).where(
                    StudentExamScore.student_id == tool_context.student_id,
                    StudentExamScore.school_id == tool_context.school_id
                )
                .order_by(Exam.start_date.desc())
                .limit(limit)
            )
            scores_with_exams = scores_result.all()

            if not scores_with_exams:
                return ToolResult(
                    ok=False,
                    error_code="NO_EXAM_FOUND",
                    error_message="未找到考试记录",
                    data={}
                )

            # 构造总分趋势
            total_trend = []
            evidence = []
            for score, exam in reversed(scores_with_exams):
                total_trend.append({
                    "exam_id": str(exam.id),
                    "exam_name": exam.name,
                    "exam_date": exam.start_date.isoformat() if exam.start_date else None,
                    "total_score": float(score.total_score),
                    "full_score": float(score.full_score) if score.full_score else None,
                    "class_rank": score.class_rank,
                    "grade_rank": score.grade_rank
                })
                evidence.append(
                    EvidenceRef(
                        type="student_exam_score",
                        resource_id=str(score.id),
                        label=exam.name,
                        as_of=score.updated_at
                    )
                )

            result_data = {
                "exam_count": len(total_trend),
                "total_trend": total_trend
            }

            # 如果指定了科目，查询科目趋势
            if subject_name:
                from app.db.models.score import StudentSubjectScore

                subject_result = await self.db.execute(
                    select(Subject).where(
                        Subject.school_id == tool_context.school_id,
                        Subject.name.ilike(f"%{subject_name}%")
                    ).limit(1)
                )
                subject = subject_result.scalar_one_or_none()

                if subject:
                    exam_ids = [score.exam_id for score, _ in scores_with_exams]
                    subject_scores_result = await self.db.execute(
                        select(StudentSubjectScore, Exam).join(
                            Exam,
                            and_(
                                StudentSubjectScore.exam_id == Exam.id,
                                Exam.school_id == tool_context.school_id,
                            ),
                        ).where(
                            and_(
                                StudentSubjectScore.student_id == tool_context.student_id,
                                StudentSubjectScore.school_id == tool_context.school_id,
                                StudentSubjectScore.subject_id == subject.id,
                                StudentSubjectScore.exam_id.in_(exam_ids)
                            )
                        )
                        .order_by(Exam.start_date.desc())
                    )
                    subject_scores = subject_scores_result.all()

                    subject_trend = []
                    for sub_score, exam in reversed(subject_scores):
                        subject_trend.append({
                            "exam_id": str(exam.id),
                            "exam_name": exam.name,
                            "exam_date": exam.start_date.isoformat() if exam.start_date else None,
                            "score": float(sub_score.score),
                            "full_score": float(sub_score.full_score),
                            "class_rank": sub_score.class_rank,
                            "grade_rank": sub_score.grade_rank
                        })

                    result_data["subject_trend"] = {
                        "subject_name": subject.name,
                        "data": subject_trend
                    }

            return ToolResult(
                ok=True,
                data=result_data,
                evidence=evidence
            )

        except Exception as e:
            return ToolResult(
                ok=False,
                error_code="TOOL_EXECUTION_ERROR",
                error_message="数据查询失败，请稍后重试",
                data={}
            )


class GetQuestionLossTool(BaseTool):
    """获取小题丢分Tool"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    def name(self) -> str:
        return "get_question_losses"

    @property
    def description(self) -> str:
        return """
获取学生某次考试的小题丢分详情，按丢分从高到低排序。
可用于分析哪些题目丢分最多，找出薄弱环节。
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
                },
                "min_loss": {
                    "type": "number",
                    "description": "最小丢分，只返回丢分大于等于此值的题目",
                    "default": 0
                },
                "limit": {
                    "type": "integer",
                    "description": "返回前N题，默认10题",
                    "default": 10
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
        min_loss = max(float(args.get("min_loss", 0)), 0)
        limit = min(max(int(args.get("limit", 10)), 1), 20)

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

            # 查询小题得分
            query = select(QuestionScore, Subject).join(
                Subject,
                and_(
                    QuestionScore.subject_id == Subject.id,
                    Subject.school_id == tool_context.school_id,
                ),
            ).where(
                and_(
                    QuestionScore.student_id == tool_context.student_id,
                    QuestionScore.exam_id == exam_id,
                    QuestionScore.school_id == tool_context.school_id,
                    QuestionScore.lost_score >= min_loss
                )
            )

            if subject_name:
                query = query.where(Subject.name.ilike(f"%{subject_name}%"))

            query = query.order_by(QuestionScore.lost_score.desc()).limit(limit)

            result = await self.db.execute(query)
            rows = result.all()

            if not rows:
                return ToolResult(
                    ok=False,
                    error_code="NO_QUESTIONS_FOUND",
                    error_message="未找到符合条件的题目",
                    data={}
                )

            # 构造返回数据
            questions = []
            evidence = []
            total_lost = 0
            for q_score, subject in rows:
                questions.append({
                    "question_no": q_score.question_no,
                    "subject_name": subject.name,
                    "score": float(q_score.score),
                    "full_score": float(q_score.full_score),
                    "lost_score": float(q_score.lost_score),
                    "loss_rate": round(
                        float(q_score.lost_score) / float(q_score.full_score) * 100, 2
                    ) if q_score.full_score else 0,
                    "answer_status": q_score.answer_status
                })
                total_lost += float(q_score.lost_score)
                evidence.append(
                    EvidenceRef(
                        type="question_score",
                        resource_id=str(q_score.id),
                        label=f"{subject.name} 第{q_score.question_no}题",
                        as_of=q_score.updated_at
                    )
                )

            return ToolResult(
                ok=True,
                data={
                    "exam_id": str(exam_id),
                    "question_count": len(questions),
                    "total_lost_score": round(total_lost, 2),
                    "questions": questions
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


class GetDiagnosisTool(BaseTool):
    """获取诊断报告Tool"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    def name(self) -> str:
        return "get_diagnosis"

    @property
    def description(self) -> str:
        return """
获取学生的诊断报告，包括知识点诊断、学习建议等。
需要DIAGNOSIS权益才能使用。
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

    @property
    def required_entitlement(self) -> str:
        return "DIAGNOSIS"

    async def execute(
        self,
        tool_context: ToolContext,
        args: dict
    ) -> ToolResult:
        """执行Tool"""
        # 验证权益
        self.validate_entitlement(tool_context)

        exam_id_str = args.get("exam_id")

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

            # 查询诊断报告
            report_result = await self.db.execute(
                select(DiagnosisReport, Exam).join(
                    Exam,
                    and_(
                        DiagnosisReport.exam_id == Exam.id,
                        Exam.school_id == tool_context.school_id,
                    ),
                ).where(
                    and_(
                        DiagnosisReport.student_id == tool_context.student_id,
                        DiagnosisReport.exam_id == exam_id,
                        DiagnosisReport.school_id == tool_context.school_id
                    )
                )
            )
            result = report_result.first()

            if not result:
                return ToolResult(
                    ok=False,
                    error_code="DIAGNOSIS_NOT_FOUND",
                    error_message="未找到诊断报告",
                    data={}
                )

            report, exam = result

            return ToolResult(
                ok=True,
                data={
                    "exam_id": str(exam.id),
                    "exam_name": exam.name,
                    "report_type": report.report_type,
                    "status": report.status,
                    "structured": report.structured_json,
                    "generated_at": report.generated_at.isoformat() if report.generated_at else None
                },
                evidence=[
                    EvidenceRef(
                        type="diagnosis_report",
                        resource_id=str(report.id),
                        label=f"{exam.name}诊断报告",
                        as_of=report.updated_at
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
