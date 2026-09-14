"""Add diagnosis and chat tables

Revision ID: 004
Revises: 003
Create Date: 2026-09-10 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建诊断报告表
    op.create_table(
        'diagnosis_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('school_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('exam_id', postgresql.UUID(as_uuid=True)),
        sa.Column('subject_id', postgresql.UUID(as_uuid=True)),
        sa.Column('report_type', sa.String(50), nullable=False, comment='报告类型'),
        sa.Column('status', sa.String(20), nullable=False, server_default='generated', comment='状态'),
        sa.Column('source_system', sa.String(50), comment='来源系统'),
        sa.Column('raw_content', sa.Text, comment='原始报告内容'),
        sa.Column('structured_json', postgresql.JSONB, nullable=False, comment='结构化JSON内容'),
        sa.Column('version', sa.String(20), comment='版本'),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False, comment='生成时间'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_diagnosis_reports_school_id_schools'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], name='fk_diagnosis_reports_student_id_students'),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], name='fk_diagnosis_reports_exam_id_exams'),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], name='fk_diagnosis_reports_subject_id_subjects'),
        sa.PrimaryKeyConstraint('id', name='pk_diagnosis_reports')
    )
    op.create_index('ix_diagnosis_reports_student_id', 'diagnosis_reports', ['student_id'])
    op.create_index('ix_diagnosis_reports_exam_id', 'diagnosis_reports', ['exam_id'])

    # 创建学生权益表
    op.create_table(
        'student_entitlements',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('school_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_code', sa.String(50), nullable=False, comment='产品代码'),
        sa.Column('resource_type', sa.String(50), comment='资源类型'),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), comment='资源ID'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active', comment='状态'),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False, comment='开始时间'),
        sa.Column('expires_at', sa.DateTime(timezone=True), comment='过期时间'),
        sa.Column('source_order_id', sa.String(100), comment='来源订单ID'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_student_entitlements_school_id_schools'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], name='fk_student_entitlements_student_id_students'),
        sa.PrimaryKeyConstraint('id', name='pk_student_entitlements'),
        sa.UniqueConstraint('student_id', 'product_code', 'resource_id', name='uq_student_product_resource')
    )
    op.create_index('ix_student_entitlements_student_id', 'student_entitlements', ['student_id'])

    # 创建聊天会话表
    op.create_table(
        'chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('school_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(200), comment='会话标题'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active', comment='状态'),
        sa.Column('selected_exam_id', postgresql.UUID(as_uuid=True), comment='当前选中考试'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_message_at', sa.DateTime(timezone=True), comment='最后消息时间'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_chat_sessions_school_id_schools'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], name='fk_chat_sessions_student_id_students'),
        sa.ForeignKeyConstraint(['selected_exam_id'], ['exams.id'], name='fk_chat_sessions_selected_exam_id_exams'),
        sa.PrimaryKeyConstraint('id', name='pk_chat_sessions')
    )
    op.create_index('ix_chat_sessions_student_id', 'chat_sessions', ['student_id'])

    # 创建聊天消息表
    op.create_table(
        'chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(20), nullable=False, comment='角色: user/assistant/system'),
        sa.Column('content', sa.Text, nullable=False, comment='消息内容'),
        sa.Column('model_id', sa.String(100), comment='模型ID'),
        sa.Column('agent_run_id', postgresql.UUID(as_uuid=True), comment='Agent运行ID'),
        sa.Column('token_input', sa.Integer, comment='输入Token数'),
        sa.Column('token_output', sa.Integer, comment='输出Token数'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], name='fk_chat_messages_session_id_chat_sessions', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_chat_messages')
    )
    op.create_index('ix_chat_messages_session_id', 'chat_messages', ['session_id'])

    # 创建Agent运行记录表
    op.create_table(
        'agent_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True)),
        sa.Column('school_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('query', sa.Text, nullable=False, comment='用户查询'),
        sa.Column('intent', sa.String(50), comment='意图分类'),
        sa.Column('entitlement_level', sa.String(20), nullable=False, comment='权益等级'),
        sa.Column('status', sa.String(20), nullable=False, comment='状态'),
        sa.Column('model_profile_id', sa.String(100), comment='模型配置ID'),
        sa.Column('prompt_version', sa.String(50), comment='Prompt版本'),
        sa.Column('tool_call_count', sa.Integer, server_default='0', comment='工具调用次数'),
        sa.Column('latency_ms', sa.Integer, comment='延迟(毫秒)'),
        sa.Column('input_tokens', sa.Integer, comment='输入Token数'),
        sa.Column('output_tokens', sa.Integer, comment='输出Token数'),
        sa.Column('estimated_cost', sa.DECIMAL(10, 6), comment='估算成本'),
        sa.Column('error_code', sa.String(50), comment='错误代码'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), comment='完成时间'),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], name='fk_agent_runs_session_id_chat_sessions'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name='fk_agent_runs_school_id_schools'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], name='fk_agent_runs_student_id_students'),
        sa.PrimaryKeyConstraint('id', name='pk_agent_runs')
    )
    op.create_index('ix_agent_runs_session_id', 'agent_runs', ['session_id'])
    op.create_index('ix_agent_runs_student_id', 'agent_runs', ['student_id'])

    # 创建工具调用日志表
    op.create_table(
        'tool_call_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tool_name', sa.String(100), nullable=False, comment='工具名称'),
        sa.Column('input_json', postgresql.JSONB, nullable=False, comment='输入参数'),
        sa.Column('output_summary_json', postgresql.JSONB, comment='输出摘要'),
        sa.Column('status', sa.String(20), nullable=False, comment='状态'),
        sa.Column('latency_ms', sa.Integer, comment='延迟(毫秒)'),
        sa.Column('error_code', sa.String(50), comment='错误代码'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agent_run_id'], ['agent_runs.id'], name='fk_tool_call_logs_agent_run_id_agent_runs', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_tool_call_logs')
    )
    op.create_index('ix_tool_call_logs_agent_run_id', 'tool_call_logs', ['agent_run_id'])

    # 创建模型使用日志表
    op.create_table(
        'model_usage_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False, comment='Provider名称'),
        sa.Column('model', sa.String(100), nullable=False, comment='模型名称'),
        sa.Column('prompt_tokens', sa.Integer, nullable=False, comment='Prompt Token数'),
        sa.Column('completion_tokens', sa.Integer, nullable=False, comment='Completion Token数'),
        sa.Column('total_tokens', sa.Integer, nullable=False, comment='总Token数'),
        sa.Column('estimated_cost', sa.DECIMAL(10, 6), comment='估算成本'),
        sa.Column('latency_ms', sa.Integer, comment='延迟(毫秒)'),
        sa.Column('agent_run_id', postgresql.UUID(as_uuid=True), comment='Agent运行ID'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_model_usage_logs')
    )


def downgrade() -> None:
    op.drop_table('model_usage_logs')
    op.drop_table('tool_call_logs')
    op.drop_table('agent_runs')
    op.drop_table('chat_messages')
    op.drop_table('chat_sessions')
    op.drop_table('student_entitlements')
    op.drop_table('diagnosis_reports')
