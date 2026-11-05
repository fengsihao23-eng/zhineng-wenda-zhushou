"""Keep the operation's target school separate from the operator's identity."""
from alembic import op
import sqlalchemy as sa

revision = "028_school_operator_audit"
down_revision = "027_admin_invitations"
branch_labels = None
depends_on = None


def upgrade():
    # Revision 024 imports the live model; a fresh database may already have
    # the new relationship while an existing deployment still has the old one.
    names = {key["name"] for key in sa.inspect(op.get_bind()).get_foreign_keys("answer_operations")}
    if "fk_answer_operation_user" in names:
        op.drop_constraint("fk_answer_operation_user", "answer_operations", type_="foreignkey")
    if "fk_answer_operation_actor" not in names:
        op.create_foreign_key("fk_answer_operation_actor", "answer_operations", "users", ["user_id"], ["id"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM answer_operations a JOIN users u ON u.id = a.user_id WHERE a.school_id <> u.school_id)")):
        raise RuntimeError("Cross-school operator history exists; retain it before downgrading this relationship")
    op.drop_constraint("fk_answer_operation_actor", "answer_operations", type_="foreignkey")
    op.create_foreign_key("fk_answer_operation_user", "answer_operations", "users", ["school_id", "user_id"], ["school_id", "id"])
