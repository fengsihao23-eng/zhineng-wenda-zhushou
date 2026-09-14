"""Enforce school/child consistency with composite foreign keys.

The child tables already carried ``school_id`` columns and route queries
filtered them, but independent foreign keys allowed a malformed row to pair a
student/exam from another school.  These constraints make that invariant hold
at the database boundary as well.
"""
from alembic import op


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, name in (
        ("users", "uq_users_school_id_id"),
        ("students", "uq_students_school_id_id"),
        ("exams", "uq_exams_school_id_id"),
        ("subjects", "uq_subjects_school_id_id"),
        ("chat_sessions", "uq_chat_sessions_school_id_id"),
        ("agent_runs", "uq_agent_runs_school_id_id"),
    ):
        op.create_unique_constraint(name, table, ["school_id", "id"])

    constraints = (
        ("fk_user_roles_school_user", "user_roles", "users", ["school_id", "user_id"], ["school_id", "id"]),
        ("fk_students_school_user", "students", "users", ["school_id", "user_id"], ["school_id", "id"]),
        ("fk_student_exam_scores_school_student", "student_exam_scores", "students", ["school_id", "student_id"], ["school_id", "id"]),
        ("fk_student_exam_scores_school_exam", "student_exam_scores", "exams", ["school_id", "exam_id"], ["school_id", "id"]),
        ("fk_student_subject_scores_school_student", "student_subject_scores", "students", ["school_id", "student_id"], ["school_id", "id"]),
        ("fk_student_subject_scores_school_exam", "student_subject_scores", "exams", ["school_id", "exam_id"], ["school_id", "id"]),
        ("fk_student_subject_scores_school_subject", "student_subject_scores", "subjects", ["school_id", "subject_id"], ["school_id", "id"]),
        ("fk_question_scores_school_student", "question_scores", "students", ["school_id", "student_id"], ["school_id", "id"]),
        ("fk_question_scores_school_exam", "question_scores", "exams", ["school_id", "exam_id"], ["school_id", "id"]),
        ("fk_question_scores_school_subject", "question_scores", "subjects", ["school_id", "subject_id"], ["school_id", "id"]),
        ("fk_chat_sessions_school_student", "chat_sessions", "students", ["school_id", "student_id"], ["school_id", "id"]),
        ("fk_agent_runs_school_student", "agent_runs", "students", ["school_id", "student_id"], ["school_id", "id"]),
        ("fk_agent_runs_school_session", "agent_runs", "chat_sessions", ["school_id", "session_id"], ["school_id", "id"]),
        ("fk_diagnosis_reports_school_student", "diagnosis_reports", "students", ["school_id", "student_id"], ["school_id", "id"]),
        ("fk_diagnosis_reports_school_exam", "diagnosis_reports", "exams", ["school_id", "exam_id"], ["school_id", "id"]),
        ("fk_diagnosis_reports_school_subject", "diagnosis_reports", "subjects", ["school_id", "subject_id"], ["school_id", "id"]),
        ("fk_student_entitlements_school_student", "student_entitlements", "students", ["school_id", "student_id"], ["school_id", "id"]),
    )
    for name, source, referent, local_cols, remote_cols in constraints:
        op.create_foreign_key(name, source, referent, local_cols, remote_cols)


def downgrade() -> None:
    for name, source, _referent, _local, _remote in (
        ("fk_student_entitlements_school_student", "student_entitlements", "students", [], []),
        ("fk_diagnosis_reports_school_subject", "diagnosis_reports", "subjects", [], []),
        ("fk_diagnosis_reports_school_exam", "diagnosis_reports", "exams", [], []),
        ("fk_diagnosis_reports_school_student", "diagnosis_reports", "students", [], []),
        ("fk_agent_runs_school_session", "agent_runs", "chat_sessions", [], []),
        ("fk_agent_runs_school_student", "agent_runs", "students", [], []),
        ("fk_chat_sessions_school_student", "chat_sessions", "students", [], []),
        ("fk_question_scores_school_subject", "question_scores", "subjects", [], []),
        ("fk_question_scores_school_exam", "question_scores", "exams", [], []),
        ("fk_question_scores_school_student", "question_scores", "students", [], []),
        ("fk_student_subject_scores_school_subject", "student_subject_scores", "subjects", [], []),
        ("fk_student_subject_scores_school_exam", "student_subject_scores", "exams", [], []),
        ("fk_student_subject_scores_school_student", "student_subject_scores", "students", [], []),
        ("fk_student_exam_scores_school_exam", "student_exam_scores", "exams", [], []),
        ("fk_student_exam_scores_school_student", "student_exam_scores", "students", [], []),
        ("fk_students_school_user", "students", "users", [], []),
        ("fk_user_roles_school_user", "user_roles", "users", [], []),
    ):
        op.drop_constraint(name, source, type_="foreignkey")

    for table, name in (
        ("agent_runs", "uq_agent_runs_school_id_id"),
        ("chat_sessions", "uq_chat_sessions_school_id_id"),
        ("subjects", "uq_subjects_school_id_id"),
        ("exams", "uq_exams_school_id_id"),
        ("students", "uq_students_school_id_id"),
        ("users", "uq_users_school_id_id"),
    ):
        op.drop_constraint(name, table, type_="unique")
