"""Persist v17 exam rosters, imports, query grants and operation history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "022_exam_management"
down_revision = "021_teaching_assignment_history"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("question_scores", "full_score", existing_type=sa.Numeric(10, 2), nullable=True)
    op.alter_column("question_scores", "lost_score", existing_type=sa.Numeric(10, 2), nullable=True)
    op.create_table('exam_administrations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('school_id', sa.Uuid(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('configuration', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['school_id', 'id'], ['exams.school_id', 'exams.id'], name='fk_exam_admin_tenant'),
        sa.ForeignKeyConstraint(['id'], ['exams.id'], name='fk_exam_administrations_id_exams'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_exam_administrations_school_id_schools'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_exam_administrations_school_id', 'exam_administrations', ['school_id'], unique=False)
    op.create_table('exam_participants',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('school_id', sa.Uuid(), nullable=False),
        sa.Column('exam_id', sa.Uuid(), nullable=False),
        sa.Column('subject_id', sa.Uuid(), nullable=False),
        sa.Column('student_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['school_id', 'exam_id'], ['exams.school_id', 'exams.id'], name='fk_exam_participant_exam'),
        sa.ForeignKeyConstraint(['school_id', 'student_id'], ['students.school_id', 'students.id'], name='fk_exam_participant_student'),
        sa.ForeignKeyConstraint(['school_id', 'subject_id'], ['subjects.school_id', 'subjects.id'], name='fk_exam_participant_subject'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_exam_participants_school_id_schools'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exam_id', 'subject_id', 'student_id', name='uq_exam_participant'),
    )
    op.create_index('ix_exam_participants_exam_id', 'exam_participants', ['exam_id'], unique=False)
    op.create_index('ix_exam_participants_student_id', 'exam_participants', ['student_id'], unique=False)
    op.create_table('exam_query_policies',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('school_id', sa.Uuid(), nullable=False),
        sa.Column('exam_id', sa.Uuid(), nullable=False),
        sa.Column('recipient_kind', sa.String(20), nullable=False),
        sa.Column('recipient_id', sa.Uuid(), nullable=False),
        sa.Column('configuration', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(['school_id', 'exam_id'], ['exams.school_id', 'exams.id'], name='fk_exam_policy_exam'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_exam_query_policies_school_id_schools'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exam_id', 'recipient_kind', 'recipient_id', name='uq_exam_query_policy'),
    )
    op.create_index('ix_exam_query_policies_exam_id', 'exam_query_policies', ['exam_id'], unique=False)
    op.create_table('exam_query_grants',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('school_id', sa.Uuid(), nullable=False),
        sa.Column('exam_id', sa.Uuid(), nullable=False),
        sa.Column('recipient_kind', sa.String(20), nullable=False),
        sa.Column('recipient_id', sa.Uuid(), nullable=False),
        sa.Column('student_id', sa.Uuid(), nullable=False),
        sa.Column('subject_id', sa.Uuid(), nullable=False),
        sa.Column('content_type', sa.String(60), nullable=False),
        sa.ForeignKeyConstraint(['school_id', 'exam_id'], ['exams.school_id', 'exams.id'], name='fk_exam_grant_exam'),
        sa.ForeignKeyConstraint(['school_id', 'student_id'], ['students.school_id', 'students.id'], name='fk_exam_grant_student'),
        sa.ForeignKeyConstraint(['school_id', 'subject_id'], ['subjects.school_id', 'subjects.id'], name='fk_exam_grant_subject'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_exam_query_grants_school_id_schools'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exam_id', 'recipient_kind', 'recipient_id', 'student_id', 'subject_id', 'content_type', name='uq_exam_query_grant'),
    )
    op.create_index('ix_exam_grant_lookup', 'exam_query_grants', ['school_id', 'recipient_kind', 'recipient_id', 'exam_id'], unique=False)
    op.create_table('exam_score_files',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('school_id', sa.Uuid(), nullable=False),
        sa.Column('exam_id', sa.Uuid(), nullable=False),
        sa.Column('subject_id', sa.Uuid(), nullable=False),
        sa.Column('filename', sa.String(200), nullable=False),
        sa.Column('original_content', sa.LargeBinary(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('rows', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['school_id', 'exam_id'], ['exams.school_id', 'exams.id'], name='fk_exam_score_file_exam'),
        sa.ForeignKeyConstraint(['school_id', 'subject_id'], ['subjects.school_id', 'subjects.id'], name='fk_exam_score_file_subject'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_exam_score_files_school_id_schools'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_exam_score_files_exam_id', 'exam_score_files', ['exam_id'], unique=False)
    op.create_index('ix_exam_score_files_school_id', 'exam_score_files', ['school_id'], unique=False)
    op.create_index('uq_exam_score_file_active', 'exam_score_files', ['school_id', 'exam_id', 'subject_id'], unique=True,
                    postgresql_where=sa.text("status = 'imported'"))
    op.create_table('exam_operations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('school_id', sa.Uuid(), nullable=False),
        sa.Column('exam_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('actor_id', sa.Uuid(), nullable=False),
        sa.Column('operator_name', sa.String(100), nullable=False),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['school_id', 'exam_id'], ['exams.school_id', 'exams.id'], name='fk_exam_operation_exam'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_exam_operations_school_id_schools'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_exam_operations_exam_id', 'exam_operations', ['exam_id'], unique=False)
    op.create_index('ix_exam_operations_school_id', 'exam_operations', ['school_id'], unique=False)


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM question_scores WHERE full_score IS NULL OR lost_score IS NULL")):
        raise RuntimeError("Question scores with unknown maxima exist; preserve them before downgrading.")
    op.drop_table('exam_operations')
    op.drop_table('exam_score_files')
    op.drop_table('exam_query_grants')
    op.drop_table('exam_query_policies')
    op.drop_table('exam_participants')
    op.drop_table('exam_administrations')
    op.alter_column("question_scores", "full_score", existing_type=sa.Numeric(10, 2), nullable=False)
    op.alter_column("question_scores", "lost_score", existing_type=sa.Numeric(10, 2), nullable=False)
