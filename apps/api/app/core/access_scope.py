"""Single management data-scope policy, including correlated teaching grants."""
from datetime import datetime, timezone

from sqlalchemy import and_, exists, or_, select, case

from app.db.models.student import Student
from app.db.models.teaching import TeachingAssignment
from app.db.models.exam import Subject
from app.db.models.import_batch import ImportedClass
from app.db.models.student_roster import StudentExamPlacement


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
    from app.db.models.exam_management import ExamQueryGrant
    return select(Student.id).where(
        Student.school_id == user.school_id,
        Student.status == "active",
        or_(exists(select(TeachingAssignment.id).where(
            *active_grants(user), assigned_class(),
        )), exists(select(ExamQueryGrant.id).where(ExamQueryGrant.school_id == user.school_id,
            ExamQueryGrant.recipient_kind == "teacher", ExamQueryGrant.recipient_id == user.user_id,
            ExamQueryGrant.student_id == Student.id))),
    )


def placement_columns(exam_id):
    query = select(StudentExamPlacement.id).where(StudentExamPlacement.school_id == Student.school_id,
                                                 StudentExamPlacement.student_id == Student.id,
                                                 StudentExamPlacement.exam_id == exam_id).correlate_except(StudentExamPlacement)
    historic = exists(query)
    class_id = query.with_only_columns(StudentExamPlacement.class_id).scalar_subquery()
    external = query.with_only_columns(StudentExamPlacement.external_class_id).scalar_subquery()
    return case((historic, class_id), else_=Student.class_id), case((historic, external), else_=Student.external_class_id)


def assigned_class(exam_id=None):
    """Support the existing CSV external-class mapping without rewriting it.

    An explicit class ID always wins. Only an unbound student can resolve its
    existing external ID through the same-school unique class mapping.
    """
    class_id, external = (Student.class_id, Student.external_class_id) if exam_id is None else placement_columns(exam_id)
    return or_(TeachingAssignment.class_id == class_id, and_(
        class_id.is_(None),
        exists(select(ImportedClass.id).where(
            ImportedClass.id == TeachingAssignment.class_id,
            ImportedClass.school_id == Student.school_id,
            ImportedClass.external_class_id == external,
        ).correlate(Student, TeachingAssignment)),
    ))


def scoped(query, user, school_column, score_type="student"):
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
        if "exam_id" in table.c:
            historic_ids = select(Student.id).where(Student.school_id == user.school_id, Student.status == "active",
                exists(select(TeachingAssignment.id).where(*active_grants(user), assigned_class(table.c.exam_id))))
            from app.core.exam_access import managed, teacher_condition
            management = managed(table.c.exam_id, table.c.school_id)
            return query.where(or_(and_(~management, table.c.student_id.in_(historic_ids)),
                and_(management, teacher_condition(table, user, score_type))))
        return query.where(table.c.student_id.in_(student_ids(user)))
    if table.name == "knowledge_documents":
        return query.where(table.c.subject.in_(
            select(Subject.name).join(TeachingAssignment, TeachingAssignment.subject_id == Subject.id)
            .where(*active_grants(user), Subject.school_id == user.school_id)
        ), table.c.status == "published")
    return query


def scoped_scores(query, user, model, view_type="student"):
    query = scoped(query, user, model.school_id, score_type=view_type).execution_options(exam_view_type=view_type)
    if is_teacher_only(user):
        # Correlate the subject grant with THIS student's class, never a union
        # of all subjects taught in unrelated classes.
        from app.core.exam_access import managed
        query = query.where(or_(managed(model.exam_id, model.school_id), exists(select(TeachingAssignment.id).join(
            Student, assigned_class(model.exam_id),
        ).where(
            *active_grants(user), Student.school_id == user.school_id,
            Student.id == model.student_id,
            TeachingAssignment.subject_id == model.subject_id,
        ))))
    return query
