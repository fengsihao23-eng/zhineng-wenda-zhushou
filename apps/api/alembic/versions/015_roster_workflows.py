"""0922 roster flows. Downgrade fails on incompatible identities; no data rewriting."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "015_roster_workflows"
down_revision = "014_education_workbench"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("account_type", sa.String(20), nullable=False, server_default="general"))
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("password_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("phone", sa.String(100)))
    op.execute("""UPDATE users SET account_type = CASE
        WHEN EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON ur.role_id=r.id WHERE ur.user_id=users.id AND ur.school_id=users.school_id AND r.code='TEACHER') THEN 'teacher'
        WHEN EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON ur.role_id=r.id WHERE ur.user_id=users.id AND ur.school_id=users.school_id AND r.code='STUDENT') THEN 'student'
        WHEN EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON ur.role_id=r.id WHERE ur.user_id=users.id AND ur.school_id=users.school_id AND r.code='PARENT') THEN 'parent'
        ELSE 'general' END""")
    op.drop_constraint("uq_school_username", "users", type_="unique")
    op.create_unique_constraint("uq_school_account_username", "users", ["school_id", "account_type", "username"])
    op.add_column("students", sa.Column("profile_fields", JSONB, nullable=False, server_default="{}"))
    op.drop_constraint("uq_school_student_no", "students", type_="unique")
    op.create_table("teacher_profiles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("school_id", UUID, sa.ForeignKey("schools.id"), nullable=False, index=True),
        sa.Column("fields", JSONB, nullable=False), sa.Column("duties", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["school_id", "id"], ["users.school_id", "users.id"], name="fk_teacher_profile_user"))
    op.create_table("roster_imports",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("school_id", UUID, sa.ForeignKey("schools.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False), sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("rows", JSONB, nullable=False),
        sa.Column("report", JSONB, nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("created_by", UUID, nullable=False),
        sa.Column("operator_name", sa.String(100), nullable=False), sa.Column("confirmation", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)))
    op.create_table("student_parent_bindings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("school_id", UUID, sa.ForeignKey("schools.id"), nullable=False, index=True),
        sa.Column("student_id", UUID, nullable=False), sa.Column("parent_user_id", UUID, nullable=False),
        sa.Column("phone", sa.String(100), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_parent_binding_student"),
        sa.ForeignKeyConstraint(["school_id", "parent_user_id"], ["users.school_id", "users.id"], name="fk_parent_binding_parent"),
        sa.UniqueConstraint("student_id", "parent_user_id", name="uq_student_parent_binding"))
    # Shared role definitions must exist before concurrent school imports.
    op.execute("""INSERT INTO roles (id, code, name) VALUES
        (gen_random_uuid(), 'TEACHER', '任课教师'), (gen_random_uuid(), 'STUDENT', '学生'),
        (gen_random_uuid(), 'PARENT', '家长'), (gen_random_uuid(), 'HOMEROOM_TEACHER', '班主任'),
        (gen_random_uuid(), 'SUBJECT_LEADER', '备课 / 教研组长'), (gen_random_uuid(), 'GRADE_LEADER', '年级长'),
        (gen_random_uuid(), 'ACADEMIC_DIRECTOR', '教务主任'), (gen_random_uuid(), 'PRINCIPAL', '校长'),
        (gen_random_uuid(), 'GENERAL_DIRECTOR', '总务主任'), (gen_random_uuid(), 'SCHOOL_VIEWER', '全校基础数据查看')
        ON CONFLICT (code) DO NOTHING""")


def downgrade():
    op.create_unique_constraint("uq_school_username", "users", ["school_id", "username"])
    op.create_unique_constraint("uq_school_student_no", "students", ["school_id", "student_no"])
    for table in ("student_parent_bindings", "roster_imports", "teacher_profiles"):
        op.drop_table(table)
    op.drop_column("students", "profile_fields")
    op.drop_constraint("uq_school_account_username", "users", type_="unique")
    for column in ("phone", "password_version", "must_change_password", "account_type"):
        op.drop_column("users", column)
