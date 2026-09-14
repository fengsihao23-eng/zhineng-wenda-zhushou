"""Add audit_logs and prompt_templates tables

Revision ID: 005
Revises: 004
Create Date: 2026-09-10 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 prompt_templates 表
    op.create_table(
        'prompt_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('scene', sa.String(50), nullable=False),
        sa.Column('version', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('variables', postgresql.JSONB),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('description', sa.Text),
        sa.Column('created_by', postgresql.UUID(as_uuid=True)),
        sa.Column('created_at', sa.TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('name', 'version', name='uq_prompt_name_version')
    )
    op.create_index('idx_prompt_name_status', 'prompt_templates', ['name', 'status'])
    op.create_index('idx_prompt_scene', 'prompt_templates', ['scene'])

    # 创建 audit_logs 表
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('actor_type', sa.String(50), nullable=False),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_type', sa.String(50)),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True)),
        sa.Column('allowed', sa.Boolean, nullable=False),
        sa.Column('reason', sa.String(200)),
        sa.Column('metadata', postgresql.JSONB),
        sa.Column('ip_address', postgresql.INET),
        sa.Column('user_agent', sa.Text),
        sa.Column('request_id', sa.String(100)),
        sa.Column('created_at', sa.TIMESTAMP, nullable=False, server_default=sa.func.now())
    )
    op.create_index('idx_audit_logs_actor', 'audit_logs', ['actor_id', 'created_at'])
    op.create_index('idx_audit_logs_resource', 'audit_logs', ['resource_type', 'resource_id'])
    op.create_index('idx_audit_logs_action', 'audit_logs', ['action', 'allowed', 'created_at'])


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('prompt_templates')
