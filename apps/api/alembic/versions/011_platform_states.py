"""Guard platform states, record outcomes and prevent lost concurrent updates.

Existing invalid states deliberately block the migration for manual review.
No existing workflow or student record is deleted or rewritten.
"""
from alembic import op
import sqlalchemy as sa

revision = "011_platform_states"
down_revision = "010_access_scope"
branch_labels = None
depends_on = None

STATES = {
    "risk_events": "'open', 'acknowledged', 'resolved', 'closed'",
    "platform_feedback": "'open', 'acknowledged', 'resolved', 'closed'",
    "human_handoffs": "'open', 'accepted', 'resolved', 'closed'",
    "knowledge_documents": "'draft', 'pending_review', 'published', 'rejected', 'offline'",
}


def upgrade():
    for table, states in STATES.items():
        op.add_column(table, sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"))
        op.create_check_constraint("valid_status", table, f"status IN ({states})")
        op.create_check_constraint("positive_state_version", table, "state_version >= 1")
    for table in ("risk_events", "human_handoffs"):
        op.add_column(table, sa.Column("resolution", sa.String(1000)))


def downgrade():
    for table in ("risk_events", "human_handoffs"):
        op.drop_column(table, "resolution")
    for table in reversed(STATES):
        op.drop_constraint(op.f(f"ck_{table}_positive_state_version"), table, type_="check")
        op.drop_constraint(op.f(f"ck_{table}_valid_status"), table, type_="check")
        op.drop_column(table, "state_version")
