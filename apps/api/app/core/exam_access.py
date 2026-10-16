"""Explicit permissions for managed exams, shared by analytics and agent tools.

Legacy exams retain their existing access policy. New managed exams start closed.
Session criteria also cover column-only/count queries and joins, preventing a
forgotten page or Tool query from bypassing a student's subject authorization.
"""
from sqlalchemy import and_, or_, select, exists, event
from sqlalchemy.orm import Session, with_loader_criteria
from app.db.models.exam_management import ExamAdministration, ExamQueryGrant, ExamParticipant
from app.db.models.score import StudentExamScore, StudentSubjectScore, QuestionScore
from app.db.models.diagnosis import DiagnosisReport


def managed(exam_id, school_id):
    return exists(select(ExamAdministration.id).where(ExamAdministration.id == exam_id,
        ExamAdministration.school_id == school_id).correlate_except(ExamAdministration))


def explicit_grant(school_id, exam_id, student_id, subject_id, recipient_kind, recipient_id, content_type):
    g = ExamQueryGrant
    conditions = [g.school_id == school_id, g.exam_id == exam_id, g.student_id == student_id,
                  g.recipient_kind == recipient_kind, g.recipient_id == recipient_id]
    if subject_id is not None:
        conditions.append(g.subject_id == subject_id)
    if isinstance(content_type, (list, tuple)):
        conditions.append(g.content_type.in_(content_type))
    else:
        conditions.append(g.content_type == content_type)
    return exists(select(g.id).where(*conditions).correlate_except(g))


def complete_grant(school_id, exam_id, student_id, kind, recipient_id, content):
    # A combined score must never reveal a closed subject by subtraction.
    scores = StudentSubjectScore.__table__.alias("exam_access_subjects")
    missing = exists(select(scores.c.id).where(scores.c.school_id == school_id, scores.c.exam_id == exam_id,
        scores.c.student_id == student_id,
        ~explicit_grant(school_id, exam_id, student_id, scores.c.subject_id, kind, recipient_id, content)).correlate_except(scores))
    participants = ExamParticipant
    missing_participation = exists(select(participants.id).where(participants.school_id == school_id,
        participants.exam_id == exam_id, participants.student_id == student_id,
        ~explicit_grant(school_id, exam_id, student_id, participants.subject_id, kind, recipient_id, content)).correlate_except(participants))
    return and_(explicit_grant(school_id, exam_id, student_id, None, kind, recipient_id, content), ~missing, ~missing_participation)


def student_condition(model, school_id, student_id):
    table = model.__table__
    if "subject_id" in table.c:
        permitted = explicit_grant(model.school_id, model.exam_id, model.student_id, model.subject_id,
                                  "student", student_id, "student")
        if model is DiagnosisReport:
            permitted = or_(and_(model.subject_id.is_not(None), permitted),
                and_(model.subject_id.is_(None), complete_grant(model.school_id, model.exam_id, model.student_id,
                    "student", student_id, "student")))
    else:
        permitted = complete_grant(model.school_id, model.exam_id, model.student_id, "student", student_id, "student")
    return or_(~managed(model.exam_id, model.school_id), and_(model.school_id == school_id, model.student_id == student_id, permitted))


def teacher_condition(table, actor, score_type="student"):
    content = "score:"+score_type
    if table.name == "diagnosis_reports":
        content = ["diagnosis:"+score_type, "essay:chinese", "essay:english"]
    if "subject_id" in table.c:
        permitted = explicit_grant(table.c.school_id, table.c.exam_id, table.c.student_id, table.c.subject_id,
                                   "teacher", actor.user_id, content)
        if table.name == "diagnosis_reports":
            permitted = or_(and_(table.c.subject_id.is_not(None), permitted),
                and_(table.c.subject_id.is_(None), complete_grant(table.c.school_id, table.c.exam_id, table.c.student_id,
                    "teacher", actor.user_id, "diagnosis:"+score_type)))
        return permitted
    if score_type not in {"classAll", "gradeAll", "school"}:
        content = ["score:classAll", "score:gradeAll", "score:school"]
    return complete_grant(table.c.school_id, table.c.exam_id, table.c.student_id, "teacher", actor.user_id, content)


@event.listens_for(Session, "do_orm_execute")
def enforce_student_exam_access(state):
    scope = state.session.info.get("exam_student_scope")
    teacher_scope = state.session.info.get("exam_teacher_scope")
    if not (scope or teacher_scope) or not state.is_select:
        return
    for model in (StudentExamScore, StudentSubjectScore, QuestionScore, DiagnosisReport):
        if scope:
            school_id, student_id = scope
            condition = student_condition(model, school_id, student_id)
        else:
            from types import SimpleNamespace
            school_id, teacher_id = teacher_scope
            content = state.execution_options.get("exam_view_type", "student")
            condition = or_(~managed(model.exam_id, model.school_id), and_(model.school_id == school_id,
                teacher_condition(model.__table__, SimpleNamespace(user_id=teacher_id), content)))
        state.statement = state.statement.options(with_loader_criteria(model, condition, include_aliases=True))


def bind_student(db, school_id, student_id):
    db.info.pop("exam_teacher_scope", None)
    db.info["exam_student_scope"] = (school_id, student_id)


def bind_teacher(db, school_id, teacher_id):
    db.info.pop("exam_student_scope", None)
    db.info["exam_teacher_scope"] = (school_id, teacher_id)
