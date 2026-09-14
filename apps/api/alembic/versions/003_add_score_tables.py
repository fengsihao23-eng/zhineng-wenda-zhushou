"""Add score tables

Revision ID: 003
Revises: 002
Create Date: 2026-09-10 12:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建学生考试总分表
    op.create_table(
        'student_exam_scores',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('school_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('exam_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('total_score', sa.DECIMAL(10, 2), nullable=False, comment='总分'),
        sa.Column('full_score', sa.DECIMAL(10, 2), comment='满分'),
        sa.Column('class_rank', sa.Integer, comment='班级排名'),
        sa.Column('grade_rank', sa.Integer, comment='年级排名'),
        sa.Column('class_student_count', sa.Integer, comment='班级学生总数'),
        sa.Column('grade_student_count', sa.Integer, comment='年级学生总数'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_student_exam_scores_school_id_schools'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], name='fk_student_exam_scores_student_id_students'),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], name='fk_student_exam_scores_exam_id_exams'),
        sa.PrimaryKeyConstraint('id', name='pk_student_exam_scores'),
        sa.UniqueConstraint('student_id', 'exam_id', name='uq_student_exam')
    )
    op.create_index('ix_student_exam_scores_student_id', 'student_exam_scores', ['student_id'])
    op.create_index('ix_student_exam_scores_exam_id', 'student_exam_scores', ['exam_id'])

    # 创建学生科目成绩表
    op.create_table(
        'student_subject_scores',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('school_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('exam_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subject_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('score', sa.DECIMAL(10, 2), nullable=False, comment='得分'),
        sa.Column('full_score', sa.DECIMAL(10, 2), nullable=False, comment='满分'),
        sa.Column('class_rank', sa.Integer, comment='班级排名'),
        sa.Column('grade_rank', sa.Integer, comment='年级排名'),
        sa.Column('class_avg', sa.DECIMAL(10, 2), comment='班级平均分'),
        sa.Column('grade_avg', sa.DECIMAL(10, 2), comment='年级平均分'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_student_subject_scores_school_id_schools'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], name='fk_student_subject_scores_student_id_students'),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], name='fk_student_subject_scores_exam_id_exams'),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], name='fk_student_subject_scores_subject_id_subjects'),
        sa.PrimaryKeyConstraint('id', name='pk_student_subject_scores'),
        sa.UniqueConstraint('student_id', 'exam_id', 'subject_id', name='uq_student_exam_subject')
    )
    op.create_index('ix_student_subject_scores_student_id', 'student_subject_scores', ['student_id'])
    op.create_index('ix_student_subject_scores_exam_id', 'student_subject_scores', ['exam_id'])

    # 创建小题得分表
    op.create_table(
        'question_scores',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('school_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('exam_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subject_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('question_id', postgresql.UUID(as_uuid=True), comment='题目ID'),
        sa.Column('question_no', sa.String(20), nullable=False, comment='题号'),
        sa.Column('score', sa.DECIMAL(10, 2), nullable=False, comment='得分'),
        sa.Column('full_score', sa.DECIMAL(10, 2), nullable=False, comment='满分'),
        sa.Column('lost_score', sa.DECIMAL(10, 2), nullable=False, comment='丢分'),
        sa.Column('answer_status', sa.String(20), comment='答题状态'),
        sa.Column('knowledge_point_id', postgresql.UUID(as_uuid=True), comment='知识点ID'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_question_scores_school_id_schools'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], name='fk_question_scores_student_id_students'),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], name='fk_question_scores_exam_id_exams'),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], name='fk_question_scores_subject_id_subjects'),
        sa.PrimaryKeyConstraint('id', name='pk_question_scores'),
        sa.UniqueConstraint('student_id', 'exam_id', 'subject_id', 'question_no', name='uq_student_exam_subject_question')
    )
    op.create_index('ix_question_scores_student_id', 'question_scores', ['student_id'])
    op.create_index('ix_question_scores_exam_id', 'question_scores', ['exam_id'])


def downgrade() -> None:
    op.drop_table('question_scores')
    op.drop_table('student_subject_scores')
    op.drop_table('student_exam_scores')
