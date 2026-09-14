"""
数据库模型
"""
from app.db.models.school import School
from app.db.models.user import User, Role, UserRole
from app.db.models.student import Student
from app.db.models.exam import Exam, Subject, ExamSubject
from app.db.models.score import (
    StudentExamScore,
    StudentSubjectScore,
    QuestionScore,
)
from app.db.models.diagnosis import DiagnosisReport, StudentEntitlement
from app.db.models.chat import ChatSession, ChatMessage
from app.db.models.agent import AgentRun, ToolCallLog, ModelUsageLog
from app.db.models.prompt import PromptTemplate
from app.db.models.trace import AuditLog
from app.db.models.import_batch import ImportBatch, ImportRow, ImportedClass
from app.db.models.platform import (
    KnowledgeDocument,
    ParentAuthorization,
    PlatformFeedback,
    RiskEvent,
    HumanHandoff,
)

__all__ = [
    "School",
    "User",
    "Role",
    "UserRole",
    "Student",
    "Exam",
    "Subject",
    "ExamSubject",
    "StudentExamScore",
    "StudentSubjectScore",
    "QuestionScore",
    "DiagnosisReport",
    "StudentEntitlement",
    "ChatSession",
    "ChatMessage",
    "AgentRun",
    "ToolCallLog",
    "ModelUsageLog",
    "PromptTemplate",
    "AuditLog",
    "ImportBatch",
    "ImportRow",
    "ImportedClass",
    "KnowledgeDocument",
    "ParentAuthorization",
    "PlatformFeedback",
    "RiskEvent",
    "HumanHandoff",
]
