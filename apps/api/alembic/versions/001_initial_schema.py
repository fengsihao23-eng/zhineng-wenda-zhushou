"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-09-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The seed INSERT below uses gen_random_uuid().  Initialise the extension
    # as part of the migration chain so a brand-new PostgreSQL database does
    # not depend on an external init script being mounted.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # 创建学校表
    op.create_table(
        'schools',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(200), nullable=False, comment='学校名称'),
        sa.Column('code', sa.String(50), nullable=False, comment='学校代码'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active', comment='状态'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_schools'),
        sa.UniqueConstraint('code', name='uq_schools_code')
    )

    # 创建角色表
    op.create_table(
        'roles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('code', sa.String(50), nullable=False, comment='角色代码'),
        sa.Column('name', sa.String(100), nullable=False, comment='角色名称'),
        sa.Column('description', sa.String(500), comment='描述'),
        sa.PrimaryKeyConstraint('id', name='pk_roles'),
        sa.UniqueConstraint('code', name='uq_roles_code')
    )

    # 插入默认角色
    op.execute("""
        INSERT INTO roles (id, code, name, description) VALUES
        (gen_random_uuid(), 'SUPER_ADMIN', '超级管理员', '系统最高权限'),
        (gen_random_uuid(), 'SCHOOL_ADMIN', '学校管理员', '学校级管理权限'),
        (gen_random_uuid(), 'TEACHER', '教师', '教师权限'),
        (gen_random_uuid(), 'STUDENT', '学生', '学生权限'),
        (gen_random_uuid(), 'QA', '测试人员', '测试权限')
    """)

    # 创建用户表
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('school_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(100), nullable=False, comment='用户名'),
        sa.Column('password_hash', sa.String(255), nullable=False, comment='密码哈希'),
        sa.Column('display_name', sa.String(100), comment='显示名称'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active', comment='状态'),
        sa.Column('last_login_at', sa.DateTime(timezone=True), comment='最后登录时间'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_users_school_id_schools'),
        sa.PrimaryKeyConstraint('id', name='pk_users'),
        sa.UniqueConstraint('school_id', 'username', name='uq_school_username')
    )
    op.create_index('ix_users_school_id', 'users', ['school_id'])

    # 创建用户角色表
    op.create_table(
        'user_roles',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('school_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_roles_user_id_users', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name='fk_user_roles_role_id_roles', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_user_roles_school_id_schools'),
        sa.PrimaryKeyConstraint('user_id', 'role_id', name='pk_user_roles')
    )
    op.create_index('ix_user_roles_school_id', 'user_roles', ['school_id'])


def downgrade() -> None:
    op.drop_table('user_roles')
    op.drop_table('users')
    op.drop_table('roles')
    op.drop_table('schools')
