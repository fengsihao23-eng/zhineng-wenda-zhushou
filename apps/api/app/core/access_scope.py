"""Single management data-scope policy, including correlated teaching grants."""
from datetime import datetime, timezone

from sqlalchemy import and_, exists, or_, select

from app.db.models.student import Student
from app.db.models.teaching import TeachingAssignment
from app.db.models.exam import Subject
from app.db.models.import_batch import ImportedClass


def is_city(user):
    return user.has_role("CITY_OPERATOR") or user.has_role("SUPER_ADMIN")


def is_teacher_only(user):
    return user.has_role("TEACHER") and not any(user.has_role(role) for role in ("SCHOOL_ADMIN", "QA", "CITY_OPERATOR", "SUPER_ADMIN", "SCHOOL_VIEWER"))


def active_grants(user):
    now = datetime.now(timezone.utc)
    return (
        TeachingAssignment.school_id == user.school_id,
        TeachingAssignment.teacher_user_id == user.user_id,
        TeachingAssignment.status == "active",
        TeachingAssignment.starts_at <= now,
        or_(TeachingAssignment.expires_at.is_(None), TeachingAssignment.expires_at > now),
    )


def student_ids(user):
    return select(Student.id).where(
        Student.school_id == user.school_id,
        Student.status == "active",
        exists(select(TeachingAssignment.id).where(
            *active_grants(user), assigned_class(),
        )),
    )


def assigned_class():
    """Support the existing CSV external-class mapping without rewriting it.

    An explicit class ID always wins. Only an unbound student can resolve its
    existing external ID through the same-school unique class mapping.
    """
    return or_(TeachingAssignment.class_id == Student.class_id, and_(
        Student.class_id.is_(None),
        exists(select(ImportedClass.id).where(
            ImportedClass.id == TeachingAssignment.class_id,
            ImportedClass.school_id == Student.school_id,
            ImportedClass.external_class_id == Student.external_class_id,
        )),
    ))


def scoped(query, user, school_column):
    """Apply tenancy and, for teachers, class-level queues/rosters or subject docs."""
    if is_city(user):
        return query
    query = query.where(school_column == user.school_id)
    if not is_teacher_only(user):
        return query
    table = school_column.table
    if table.name == "students":
        return query.where(table.c.id.in_(student_ids(user)))
    if "student_id" in table.c:
        return query.where(table.c.student_id.in_(student_ids(user)))
    if table.name == "knowledge_documents":
        return query.where(table.c.subject.in_(
            select(Subject.name).join(TeachingAssignment, TeachingAssignment.subject_id == Subject.id)
            .where(*active_grants(user), Subject.school_id == user.school_id)
        ), table.c.status == "published")
    return query


def scoped_scores(query, user, model):
    query = scoped(query, user, model.school_id)
    if is_teacher_only(user):
        # Correlate the subject grant with THIS student's class, never a union
        # of all subjects taught in unrelated classes.
        query = query.where(exists(select(TeachingAssignment.id).join(
            Student, assigned_class(),
        ).where(
            *active_grants(user), Student.school_id == user.school_id,
            Student.id == model.student_id,
            TeachingAssignment.subject_id == model.subject_id,
        )))
    return query
