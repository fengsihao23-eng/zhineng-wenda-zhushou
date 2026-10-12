"""Student r79: reviewed batch workflows, academic years and historical placements."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "019_student_r79_workflows"
down_revision = "018_teacher_change_tasks"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("schools", sa.Column("current_academic_year", sa.String(20)))
    op.add_column("students", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.alter_column("students", "student_no", existing_type=sa.String(50), type_=sa.String(5000))
    for name in ("student_year_classes", "student_exam_placements"):
        columns = [
            sa.Column("id", UUID, primary_key=True),
            sa.Column("school_id", UUID, sa.ForeignKey("schools.id"), nullable=False),
            sa.Column("student_id", UUID, nullable=False),
            sa.Column("academic_year", sa.String(20), nullable=False),
            sa.Column("grade", sa.String(5000), nullable=False, server_default=""),
            sa.Column("class_number", sa.String(5000), nullable=False, server_default=""),
            sa.Column("class_id", UUID),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_student_year_student" if name == "student_year_classes" else "fk_placement_student"),
        ]
        if name == "student_year_classes":
            columns += [sa.Column("status", sa.String(20), nullable=False, server_default="active"),
                        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                        sa.UniqueConstraint("school_id", "student_id", "academic_year", name="uq_student_year_class")]
        else:
            columns += [sa.Column("exam_id", UUID, nullable=False), sa.Column("external_class_id", sa.String(100)),
                        sa.ForeignKeyConstraint(["school_id", "exam_id"], ["exams.school_id", "exams.id"], name="fk_placement_exam"),
                        sa.UniqueConstraint("school_id", "student_id", "exam_id", name="uq_student_exam_placement")]
        op.create_table(name, *columns)
        for column in ("school_id", "student_id", *(("exam_id",) if name == "student_exam_placements" else ())):
            op.create_index(f"ix_{name}_{column}", name, [column])
    op.create_table(
        "student_workflow_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("school_id", UUID, sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="ready"),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("filename", sa.String(200)),
        sa.Column("original_content", sa.LargeBinary),
        sa.Column("request_payload", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("rows", JSONB, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("snapshots", JSONB, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("report", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("preparation", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("reviews", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("confirmation", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("operator_name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )
    for column in ("school_id", "kind", "status"):
        op.create_index(f"ix_student_workflow_tasks_{column}", "student_workflow_tasks", [column])


def downgrade():
    for name in ("student_workflow_tasks", "student_year_classes", "student_exam_placements"):
        if op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {name}")):
            raise RuntimeError("Student workflow/history data exists; preserve it before downgrading.")
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM students WHERE length(student_no) > 50")):
        raise RuntimeError("Student numbers exceed the old schema limit; preserve their full values.")
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM schools WHERE current_academic_year IS NOT NULL")) or op.get_bind().scalar(sa.text("SELECT count(*) FROM students WHERE archived_at IS NOT NULL")):
        raise RuntimeError("Student academic-year or graduation state exists; preserve it before downgrading.")
    op.drop_table("student_workflow_tasks")
    op.drop_table("student_exam_placements")
    op.drop_table("student_year_classes")
    op.drop_column("students", "archived_at")
    op.drop_column("schools", "current_academic_year")
    op.alter_column("students", "student_no", existing_type=sa.String(5000), type_=sa.String(50))
