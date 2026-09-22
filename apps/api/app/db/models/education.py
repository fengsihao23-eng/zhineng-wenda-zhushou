"""Education workbench records. Versions and imported evidence are immutable.

Every relationship includes school_id; APIs additionally enforce role, teaching
and student scope. Files are private database blobs in this bounded first release.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    DateTime,
    LargeBinary,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.sql import func
from app.db.base import Base
from app.db.types import UUID, JSONB


def identity():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def school():
    return Column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True
    )


def timestamp():
    return Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


def tenant_key(table):
    return UniqueConstraint("school_id", "id", name=f"uq_{table}_tenant")


def ref(table, column, name):
    return ForeignKeyConstraint(
        ["school_id", column], [f"{table}.school_id", f"{table}.id"], name=name
    )


class SourceRecord(Base):
    __tablename__ = "education_sources"
    id = identity()
    school_id = school()
    source_system = Column(String(50), nullable=False)
    entity_type = Column(String(30), nullable=False)
    external_id = Column(String(100), nullable=False)
    source_version = Column(String(40), nullable=False)
    content_hash = Column(String(64), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    native_id = Column(UUID(as_uuid=True), nullable=False)
    payload = Column(JSONB, nullable=False)
    created_at = timestamp()
    __table_args__ = (
        tenant_key(__tablename__),
        UniqueConstraint(
            "school_id",
            "source_system",
            "entity_type",
            "external_id",
            "source_version",
            name="uq_source_version",
        ),
    )


class ImportWorkspace(Base):
    __tablename__ = "education_imports"
    id = identity()
    school_id = school()
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    batch_key = Column(String(80), nullable=False)
    source_system = Column(String(50), nullable=False)
    files = Column(JSONB, nullable=False)
    mapping = Column(JSONB, nullable=False, default=dict)
    content_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="uploaded")
    revision = Column(Integer, nullable=False, default=1)
    progress = Column(Integer, nullable=False, default=0)
    report = Column(JSONB, nullable=False, default=dict)
    created_at = timestamp()
    updated_at = timestamp()
    __table_args__ = (
        tenant_key(__tablename__),
        UniqueConstraint("school_id", "batch_key", name="uq_import_workspace_batch"),
        CheckConstraint(
            "status IN ('uploaded','invalid','ready','running','succeeded','failed')",
            name="valid_status",
        ),
    )


class MappingTemplate(Base):
    __tablename__ = "education_mapping_templates"
    id = identity()
    school_id = school()
    name = Column(String(100), nullable=False)
    version = Column(Integer, nullable=False)
    mapping = Column(JSONB, nullable=False)
    created_at = timestamp()
    __table_args__ = (
        UniqueConstraint(
            "school_id", "name", "version", name="uq_mapping_template_version"
        ),
    )


class PrivateAsset(Base):
    __tablename__ = "education_assets"
    id = identity()
    school_id = school()
    filename = Column(String(200), nullable=False)
    media_type = Column(String(80), nullable=False)
    byte_size = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=False)
    storage_key = Column(String(160), nullable=False, unique=True)
    content = Column(LargeBinary, nullable=False)
    pages = Column(JSONB, nullable=False, default=list)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = timestamp()
    __table_args__ = (tenant_key(__tablename__),)


class Paper(Base):
    __tablename__ = "education_papers"
    id = identity()
    school_id = school()
    exam_id = Column(UUID(as_uuid=True), nullable=False)
    subject_id = Column(UUID(as_uuid=True), nullable=False)
    title = Column(String(200), nullable=False)
    source_system = Column(String(50), nullable=False, default="native")
    status = Column(String(20), nullable=False, default="active")
    revision = Column(Integer, nullable=False, default=1)
    created_at = timestamp()
    __table_args__ = (
        tenant_key(__tablename__),
        ref("exams", "exam_id", "fk_paper_exam"),
        ref("subjects", "subject_id", "fk_paper_subject"),
    )


class PaperVersion(Base):
    __tablename__ = "education_paper_versions"
    id = identity()
    school_id = school()
    paper_id = Column(UUID(as_uuid=True), nullable=False)
    asset_id = Column(UUID(as_uuid=True), nullable=False)
    number = Column(Integer, nullable=False)
    source_id = Column(UUID(as_uuid=True))
    created_at = timestamp()
    __table_args__ = (
        tenant_key(__tablename__),
        ref("education_papers", "paper_id", "fk_paper_version_paper"),
        ref("education_assets", "asset_id", "fk_paper_version_asset"),
        ref("education_sources", "source_id", "fk_paper_version_source"),
        UniqueConstraint("paper_id", "number", name="uq_paper_version"),
    )


class Question(Base):
    __tablename__ = "education_questions"
    id = identity()
    school_id = school()
    subject_id = Column(UUID(as_uuid=True), nullable=False)
    kind = Column(String(20), nullable=False)
    parent_id = Column(UUID(as_uuid=True))
    title = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    source_system = Column(String(50), nullable=False, default="native")
    revision = Column(Integer, nullable=False, default=1)
    deleted_at = Column(DateTime(timezone=True))
    created_at = timestamp()
    __table_args__ = (
        tenant_key(__tablename__),
        ref("subjects", "subject_id", "fk_question_subject"),
        ref("education_questions", "parent_id", "fk_question_parent"),
        CheckConstraint(
            "kind IN ('material','major','minor','standalone')", name="valid_kind"
        ),
        CheckConstraint("status IN ('draft','published')", name="valid_status"),
    )


class QuestionVersion(Base):
    __tablename__ = "education_question_versions"
    id = identity()
    school_id = school()
    question_id = Column(UUID(as_uuid=True), nullable=False)
    number = Column(Integer, nullable=False)
    stem = Column(Text, nullable=False)
    options = Column(JSONB, nullable=False, default=list)
    answer = Column(Text, nullable=False, default="")
    explanation = Column(Text, nullable=False, default="")
    paper_version_id = Column(UUID(as_uuid=True))
    regions = Column(JSONB, nullable=False, default=list)
    source_id = Column(UUID(as_uuid=True))
    published_at = Column(DateTime(timezone=True))
    created_at = timestamp()
    __table_args__ = (
        tenant_key(__tablename__),
        ref("education_questions", "question_id", "fk_question_version_question"),
        ref(
            "education_paper_versions", "paper_version_id", "fk_question_version_paper"
        ),
        ref("education_sources", "source_id", "fk_question_version_source"),
        UniqueConstraint("question_id", "number", name="uq_question_version"),
    )


class TaxonomyNode(Base):
    __tablename__ = "education_taxonomy"
    id = identity()
    school_id = school()
    subject_id = Column(UUID(as_uuid=True), nullable=False)
    parent_id = Column(UUID(as_uuid=True))
    kind = Column(String(30), nullable=False, default="knowledge")
    name = Column(String(100), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    deleted_at = Column(DateTime(timezone=True))
    created_at = timestamp()
    __table_args__ = (
        tenant_key(__tablename__),
        ref("subjects", "subject_id", "fk_taxonomy_subject"),
        ref("education_taxonomy", "parent_id", "fk_taxonomy_parent"),
    )


class QuestionTag(Base):
    __tablename__ = "education_question_tags"
    id = identity()
    school_id = school()
    question_version_id = Column(UUID(as_uuid=True), nullable=False)
    node_id = Column(UUID(as_uuid=True), nullable=False)
    __table_args__ = (
        ref(
            "education_question_versions",
            "question_version_id",
            "fk_question_tag_version",
        ),
        ref("education_taxonomy", "node_id", "fk_question_tag_node"),
        UniqueConstraint("question_version_id", "node_id", name="uq_question_tag"),
    )


class PaperDraft(Base):
    __tablename__ = "education_paper_drafts"
    id = identity()
    school_id = school()
    paper_version_id = Column(UUID(as_uuid=True), nullable=False, unique=True)
    revision = Column(Integer, nullable=False, default=1)
    entries = Column(JSONB, nullable=False, default=list)
    published_revision = Column(Integer)
    published_ids = Column(JSONB, nullable=False, default=list)
    updated_at = timestamp()
    __table_args__ = (
        tenant_key(__tablename__),
        ref("education_paper_versions", "paper_version_id", "fk_draft_paper_version"),
    )


class OcrJob(Base):
    __tablename__ = "education_ocr_jobs"
    id = identity()
    school_id = school()
    draft_id = Column(UUID(as_uuid=True), nullable=False)
    draft_revision = Column(Integer, nullable=False)
    input_entries = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False, default="queued")
    attempt = Column(Integer, nullable=False, default=1)
    progress = Column(Integer, nullable=False, default=0)
    result = Column(JSONB, nullable=False, default=list)
    error_code = Column(String(50))
    lease_until = Column(DateTime(timezone=True))
    created_at = timestamp()
    finished_at = Column(DateTime(timezone=True))
    __table_args__ = (
        tenant_key(__tablename__),
        ref("education_paper_drafts", "draft_id", "fk_ocr_draft"),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed')", name="valid_status"
        ),
    )


class ReportAttachment(Base):
    __tablename__ = "education_report_attachments"
    id = identity()
    school_id = school()
    report_id = Column(UUID(as_uuid=True), nullable=False, unique=True)
    asset_id = Column(UUID(as_uuid=True), nullable=False)
    source_id = Column(UUID(as_uuid=True))
    created_at = timestamp()
    __table_args__ = (
        tenant_key(__tablename__),
        ref("diagnosis_reports", "report_id", "fk_attachment_report"),
        ref("education_assets", "asset_id", "fk_attachment_asset"),
        ref("education_sources", "source_id", "fk_attachment_source"),
    )


class ReviewEntry(Base):
    __tablename__ = "education_reviews"
    id = identity()
    school_id = school()
    student_id = Column(UUID(as_uuid=True), nullable=False)
    score_id = Column(UUID(as_uuid=True), nullable=False)
    question_version_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = timestamp()
    __table_args__ = (
        tenant_key(__tablename__),
        ref("students", "student_id", "fk_review_student"),
        ref("question_scores", "score_id", "fk_review_score"),
        ref("education_question_versions", "question_version_id", "fk_review_question"),
        UniqueConstraint("student_id", "score_id", name="uq_review_score"),
    )


class ReviewRecord(Base):
    __tablename__ = "education_review_records"
    id = identity()
    school_id = school()
    review_id = Column(UUID(as_uuid=True), nullable=False)
    correction = Column(Text, nullable=False)
    mastery = Column(String(20), nullable=False)
    next_review_at = Column(DateTime(timezone=True))
    created_at = timestamp()
    __table_args__ = (
        ref("education_reviews", "review_id", "fk_review_record"),
        CheckConstraint(
            "mastery IN ('learning','reviewing','mastered')", name="valid_mastery"
        ),
    )


class HandoffMessage(Base):
    __tablename__ = "education_handoff_messages"
    id = identity()
    school_id = school()
    handoff_id = Column(UUID(as_uuid=True), nullable=False)
    sender_id = Column(UUID(as_uuid=True), nullable=False)
    sender_role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = timestamp()
    __table_args__ = (
        ref("human_handoffs", "handoff_id", "fk_handoff_message_handoff"),
        ref("users", "sender_id", "fk_handoff_message_sender"),
    )
