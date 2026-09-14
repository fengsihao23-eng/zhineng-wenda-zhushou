"""Add student and exam tables

Revision ID: 002
Revises: 001
Create Date: 2026-09-10 12:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建学生表
    op.create_table(
        'students',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('school_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), comment='关联用户ID'),
        sa.Column('external_student_id', sa.String(100), comment='外部系统学生ID'),
        sa.Column('student_no', sa.String(50), comment='学号'),
        sa.Column('name', sa.String(100), nullable=False, comment='姓名'),
        sa.Column('grade_id', postgresql.UUID(as_uuid=True), comment='年级ID'),
        sa.Column('class_id', postgresql.UUID(as_uuid=True), comment='班级ID'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active', comment='状态'),
        sa.Column('source_system', sa.String(50), comment='数据来源系统'),
        sa.Column('source_updated_at', sa.DateTime(timezone=True), comment='源系统更新时间'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_students_school_id_schools'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_students_user_id_users'),
        sa.PrimaryKeyConstraint('id', name='pk_students'),
        sa.UniqueConstraint('school_id', 'external_student_id', name='uq_school_external_student'),
        sa.UniqueConstraint('school_id', 'student_no', name='uq_school_student_no')
    )
    op.create_index('ix_students_school_id', 'students', ['school_id'])
    op.create_index('ix_students_user_id', 'students', ['user_id'])

    # 创建科目表
    op.create_table(
        'subjects',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('school_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('code', sa.String(50), nullable=False, comment='科目代码'),
        sa.Column('name', sa.String(100), nullable=False, comment='科目名称'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_subjects_school_id_schools'),
        sa.PrimaryKeyConstraint('id', name='pk_subjects'),
        sa.UniqueConstraint('school_id', 'code', name='uq_school_subject_code')
    )
    op.create_index('ix_subjects_school_id', 'subjects', ['school_id'])

    # 创建考试表
    op.create_table(
        'exams',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('school_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('external_exam_id', sa.String(100), comment='外部考试ID'),
        sa.Column('name', sa.String(200), nullable=False, comment='考试名称'),
        sa.Column('exam_type', sa.String(50), nullable=False, comment='考试类型'),
        sa.Column('academic_year', sa.String(20), comment='学年'),
        sa.Column('term', sa.String(20), comment='学期'),
        sa.Column('grade_id', postgresql.UUID(as_uuid=True), comment='年级ID'),
        sa.Column('start_date', sa.Date, comment='开始日期'),
        sa.Column('end_date', sa.Date, comment='结束日期'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active', comment='状态'),
        sa.Column('source_system', sa.String(50), comment='来源系统'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_exams_school_id_schools'),
        sa.PrimaryKeyConstraint('id', name='pk_exams'),
        sa.UniqueConstraint('school_id', 'external_exam_id', name='uq_school_external_exam')
    )
    op.create_index('ix_exams_school_id', 'exams', ['school_id'])
    op.create_index('ix_exams_grade_id', 'exams', ['grade_id'])

    # 创建考试科目表
    op.create_table(
        'exam_subjects',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('exam_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subject_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('full_score', sa.DECIMAL(10, 2), nullable=False, comment='满分'),
        sa.Column('grade_avg', sa.DECIMAL(10, 2), comment='年级平均分'),
        sa.Column('class_avg', sa.DECIMAL(10, 2), comment='班级平均分'),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], name='fk_exam_subjects_exam_id_exams', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], name='fk_exam_subjects_subject_id_subjects'),
        sa.PrimaryKeyConstraint('id', name='pk_exam_subjects'),
        sa.UniqueConstraint('exam_id', 'subject_id', name='uq_exam_subject')
    )
    op.create_index('ix_exam_subjects_exam_id', 'exam_subjects', ['exam_id'])


def downgrade() -> None:
    op.drop_table('exam_subjects')
    op.drop_table('exams')
    op.drop_table('subjects')
    op.drop_table('students')
