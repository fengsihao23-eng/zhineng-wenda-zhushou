"""Persistent daily question quota and expiring presence leases."""
from alembic import op
from app.db.models.answer_workbench import AnswerDailyUsage, AnswerPresence

revision = "025_answer_usage_presence"
down_revision = "024_answer_workbench"
branch_labels = None
depends_on = None


def upgrade():
    for model in (AnswerDailyUsage, AnswerPresence):
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    for model in (AnswerPresence, AnswerDailyUsage):
        model.__table__.drop(op.get_bind(), checkfirst=True)
