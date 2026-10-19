"""School prompt and mini program workflows, additive tables only."""
from alembic import op
from app.db.models.answer_workbench import AnswerScope, AnswerTrial, AnswerSession, AnswerTicket, AnswerOperation

revision = "024_answer_workbench"
down_revision = "023_report_management"
branch_labels = None
depends_on = None


def upgrade():
    for model in (AnswerScope, AnswerTrial, AnswerSession, AnswerTicket, AnswerOperation):
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    for model in (AnswerOperation, AnswerTicket, AnswerSession, AnswerTrial, AnswerScope):
        model.__table__.drop(op.get_bind(), checkfirst=True)
