"""
数据库模型
"""
from app.db.models.education import (SourceRecord, ImportWorkspace, MappingTemplate, PrivateAsset, Paper, PaperVersion, Question, QuestionVersion, TaxonomyNode, QuestionTag, PaperDraft, OcrJob, ReportAttachment, ReviewEntry, ReviewRecord, HandoffMessage)
from app.db.models.person_id import PlatformPersonId
from app.db.models.roster import TeacherProfile, TeacherDeletion, TeacherChangeTask, RosterImport
from app.db.models.school import School
from app.db.models.security import TokenRevocation
from app.db.models.user import User, Role, UserRole
from app.db.models.student import Student
from app.db.models.student_roster import StudentYearClass, StudentExamPlacement, StudentWorkflowTask
from app.db.models.teaching import TeachingAssignment
from app.db.models.operation_receipt import OperationReceipt
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
    "PlatformPersonId",
    "School",
    "TeacherProfile",
    "TeacherDeletion",
    "TeacherChangeTask",
    "RosterImport",
    "TokenRevocation",
    "User",
    "Role",
    "UserRole",
    "Student",
    "StudentYearClass",
    "StudentExamPlacement",
    "StudentWorkflowTask",
    "TeachingAssignment",
    "OperationReceipt",
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
