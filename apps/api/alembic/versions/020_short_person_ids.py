"""Permanent 8–10 digit platform student/teacher IDs; retain every history FK."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "020_short_person_ids"
down_revision = "019_student_r79_workflows"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("LOCK TABLE users, students, teacher_deletions, roster_imports, student_workflow_tasks IN SHARE ROW EXCLUSIVE MODE")
    op.create_table(
        "platform_person_ids",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True, start=10000001, minvalue=10000001, maxvalue=9999999999, cycle=False), primary_key=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("school_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("kind", "entity_id", name="uq_platform_person_entity"),
        sa.UniqueConstraint("school_id", "entity_id", "id", name="uq_platform_person_binding"),
        sa.CheckConstraint("id BETWEEN 10000001 AND 9999999999", name="person_id_range"),
        sa.CheckConstraint("kind IN ('student', 'teacher')", name="person_id_kind"),
    )
    op.create_index("ix_platform_person_ids_school_id", "platform_person_ids", ["school_id"])
    # A single global namespace, including retired/deleted identities in retained
    # reports. Neither account names nor student/exam numbers enter allocation.
    op.execute("""
        INSERT INTO platform_person_ids(kind, entity_id, school_id)
        SELECT kind, entity_id, school_id FROM (
          SELECT 'student' AS kind, id AS entity_id, school_id FROM students
          UNION
          SELECT 'teacher', u.id, u.school_id FROM users u WHERE u.account_type = 'teacher'
            OR EXISTS (SELECT 1 FROM teacher_profiles p WHERE p.id = u.id)
            OR EXISTS (SELECT 1 FROM teacher_deletions d WHERE d.user_id = u.id)
            OR EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id
                       WHERE ur.user_id = u.id AND r.code = 'TEACHER')
          UNION
          SELECT 'student', (entry->>'id')::uuid, t.school_id
            FROM student_workflow_tasks t CROSS JOIN LATERAL jsonb_array_elements(t.snapshots) entry
            WHERE entry->>'id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
          UNION
          SELECT CASE i.kind WHEN 'students' THEN 'student' ELSE 'teacher' END, (entry->>'id')::uuid, i.school_id
            FROM roster_imports i CROSS JOIN LATERAL jsonb_array_elements(COALESCE(i.report->'imported', '[]'::jsonb)) entry
            WHERE i.status = 'succeeded' AND i.kind IN ('students', 'teachers')
              AND entry->>'id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        ) identities
        ORDER BY kind, school_id, entity_id
    """)
    for table in ("students", "users", "teacher_deletions"):
        op.add_column(table, sa.Column("platform_id", sa.BigInteger()))
    op.execute("UPDATE students s SET platform_id = p.id FROM platform_person_ids p WHERE p.kind = 'student' AND p.school_id = s.school_id AND p.entity_id = s.id")
    op.execute("UPDATE users u SET platform_id = p.id FROM platform_person_ids p WHERE p.kind = 'teacher' AND p.school_id = u.school_id AND p.entity_id = u.id")
    op.execute("UPDATE teacher_deletions d SET platform_id = p.id FROM platform_person_ids p WHERE p.kind = 'teacher' AND p.school_id = d.school_id AND p.entity_id = d.user_id")
    for table in ("students", "teacher_deletions"):
        op.alter_column(table, "platform_id", nullable=False)
    for table, source, constraint in (
        ("students", "id", "fk_student_platform_identity"),
        ("users", "id", "fk_teacher_platform_identity"),
        ("teacher_deletions", "user_id", "fk_teacher_snapshot_platform_identity"),
    ):
        op.create_foreign_key(constraint, table, "platform_person_ids", ["school_id", source, "platform_id"], ["school_id", "entity_id", "id"])
    for table in ("students", "users"):
        op.create_unique_constraint(f"uq_{table}_platform_id", table, ["platform_id"])
    for key, source in (("imported", "id"), ("versions", "teacher_id")):
        op.execute(f"""
            UPDATE roster_imports i SET report = jsonb_set(report, '{{{key}}}', (
              SELECT COALESCE(jsonb_agg(CASE WHEN p.id IS NULL THEN entry
                ELSE entry || jsonb_build_object('platform_id', p.id::text) END ORDER BY ord), '[]'::jsonb)
              FROM jsonb_array_elements(i.report->'{key}') WITH ORDINALITY entries(entry, ord)
              LEFT JOIN platform_person_ids p ON p.school_id = i.school_id AND p.entity_id::text = entry->>'{source}'
                AND p.kind = CASE i.kind WHEN 'students' THEN 'student' ELSE 'teacher' END
            )) WHERE jsonb_typeof(report->'{key}') = 'array'
        """)
    # Keep original Excel bytes intact. Snapshot metadata gains the stable short
    # identity; its UUID and fingerprint retain compatibility with pending tasks.
    op.execute("""
        UPDATE student_workflow_tasks t SET snapshots = (
          SELECT COALESCE(jsonb_agg(
            CASE WHEN p.id IS NULL THEN entry ELSE entry || jsonb_build_object(
              'platform_id', p.id::text, 'fields', COALESCE(entry->'fields', '{}'::jsonb) || jsonb_build_object('学生ID', p.id::text)) END
            ORDER BY ord), '[]'::jsonb)
          FROM jsonb_array_elements(t.snapshots) WITH ORDINALITY rows(entry, ord)
          LEFT JOIN platform_person_ids p ON p.kind = 'student' AND p.school_id = t.school_id AND p.entity_id::text = entry->>'id'
        ) WHERE jsonb_array_length(t.snapshots) > 0
    """)
    op.execute("""
        CREATE FUNCTION guard_platform_person_identity() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'Platform person identities are permanent and cannot be changed or reused';
        END $$
    """)
    op.execute("CREATE TRIGGER immutable_platform_person_identity BEFORE UPDATE OR DELETE ON platform_person_ids FOR EACH ROW EXECUTE FUNCTION guard_platform_person_identity()")
    op.execute("""
        CREATE FUNCTION guard_person_platform_id() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.platform_id IS NOT NULL AND NEW.platform_id IS DISTINCT FROM OLD.platform_id THEN
            RAISE EXCEPTION 'Platform person ID cannot be changed';
          END IF;
          RETURN NEW;
        END $$
    """)
    for table in ("students", "users", "teacher_deletions"):
        op.execute(f"CREATE TRIGGER immutable_person_platform_id BEFORE UPDATE OF platform_id ON {table} FOR EACH ROW EXECUTE FUNCTION guard_person_platform_id()")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM platform_person_ids")):
        raise RuntimeError("Assigned platform IDs must be preserved. Roll back app images without discarding the identity mapping.")
    for table in ("students", "users", "teacher_deletions"):
        op.execute(f"DROP TRIGGER immutable_person_platform_id ON {table}")
        op.drop_column(table, "platform_id")
    op.execute("DROP FUNCTION guard_person_platform_id()")
    op.drop_table("platform_person_ids")
    op.execute("DROP FUNCTION guard_platform_person_identity()")
