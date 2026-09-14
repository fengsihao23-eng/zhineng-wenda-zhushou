"""Align trace tables with the runtime ORM models.

Revision ID: 006
Revises: 005
"""
from alembic import op
import sqlalchemy as sa


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the fields and relationship omitted from the initial trace DDL."""
    op.add_column(
        "agent_runs",
        sa.Column("guard_action", sa.String(20), nullable=True),
    )
    op.create_index(
        "ix_model_usage_logs_agent_run_id",
        "model_usage_logs",
        ["agent_run_id"],
    )
    op.create_foreign_key(
        "fk_model_usage_logs_agent_run_id_agent_runs",
        "model_usage_logs",
        "agent_runs",
        ["agent_run_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_model_usage_logs_agent_run_id_agent_runs",
        "model_usage_logs",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_model_usage_logs_agent_run_id",
        table_name="model_usage_logs",
    )
    op.drop_column("agent_runs", "guard_action")
