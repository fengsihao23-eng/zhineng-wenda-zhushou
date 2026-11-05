"""Add pending administrator registration and single-use invitations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import json
from uuid import uuid4

revision = "027_admin_invitations"
down_revision = "026_score_precision"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("administrator_code", sa.String(8), nullable=True))
    op.create_unique_constraint("uq_users_administrator_code", "users", ["administrator_code"])
    op.alter_column("users", "school_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_check_constraint("user_pending_administrator_school", "users", "school_id IS NOT NULL OR (administrator_code IS NOT NULL AND status = 'pending')")
    op.create_check_constraint("user_administrator_code_username", "users", "administrator_code IS NULL OR administrator_code = username")
    op.create_check_constraint("user_administrator_code_length", "users", "administrator_code IS NULL OR length(administrator_code) = 8")
    op.create_table(
        "administrator_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("used_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active', 'used', 'revoked')", name="ck_admin_invitation_status"),
    )
    promote_legacy_admin()


def promote_legacy_admin():
    """Owner-requested upgrade of the unique existing admin, never a name-based runtime bypass."""
    conn = op.get_bind()
    candidates = conn.execute(sa.text(
        "SELECT id, school_id FROM users WHERE username = 'admin' AND account_type = 'general' AND status = 'active'"
    )).mappings().all()
    if len(candidates) > 1:
        raise RuntimeError("Multiple active admin accounts exist; identify the intended legacy admin before applying migration 027")
    if not candidates:
        return  # Fresh deployments have no owner account to upgrade.
    admin = candidates[0]
    before = list(conn.scalars(sa.text(
        "SELECT roles.code FROM roles JOIN user_roles ON user_roles.role_id = roles.id WHERE user_roles.user_id = :id AND user_roles.school_id = :school_id"
    ), {"id": admin["id"], "school_id": admin["school_id"]}))
    if "SUPER_ADMIN" in before:
        return
    if "SCHOOL_ADMIN" not in before or admin["school_id"] is None:
        raise RuntimeError("The existing admin is not the expected school administrator; verify its identity before upgrading")
    role_id = conn.scalar(sa.text("SELECT id FROM roles WHERE code = 'SUPER_ADMIN'"))
    if role_id is None:
        raise RuntimeError("SUPER_ADMIN role is missing")
    conn.execute(sa.text("INSERT INTO user_roles (user_id, role_id, school_id) VALUES (:id, :role_id, :school_id)"),
                 {"id": admin["id"], "role_id": role_id, "school_id": admin["school_id"]})
    conn.execute(sa.text("UPDATE users SET password_version = password_version + 1, updated_at = now() WHERE id = :id"), {"id": admin["id"]})
    conn.execute(sa.text("""INSERT INTO audit_logs (id, action, actor_type, actor_id, resource_type, resource_id, allowed, metadata)
        VALUES (:audit_id, 'administrator.bootstrap', 'system', :id, 'users', :id, true, CAST(:details AS jsonb))"""), {
            "audit_id": uuid4(), "id": admin["id"], "details": json.dumps({"school_id": str(admin["school_id"]),
                "before": {"roles": sorted(before)}, "after": {"roles": sorted(before + ["SUPER_ADMIN"])},
                "migration": revision, "reason": "Owner requested the existing admin to be the super administrator"}),
        })


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM users WHERE school_id IS NULL)")):
        raise RuntimeError("Assign schools to pending administrators before downgrading")
    op.drop_table("administrator_invitations")
    op.drop_constraint(op.f("ck_users_user_administrator_code_length"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_user_pending_administrator_school"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_user_administrator_code_username"), "users", type_="check")
    op.alter_column("users", "school_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_constraint("uq_users_administrator_code", "users", type_="unique")
    op.drop_column("users", "administrator_code")
