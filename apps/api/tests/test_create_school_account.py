"""Production account provisioning must work without fixtures or default secrets."""
import pytest
from sqlalchemy import func, select

from app.core.security import verify_password
from app.db.models import School, User, UserRole
from scripts.create_school_account import provision


@pytest.mark.asyncio
async def test_provision_creates_school_role_and_strong_password(test_db):
    result = await provision(
        test_db,
        school_code="441701001001",
        school_name="阳江一中",
        username="admin01",
        role_code="SCHOOL_ADMIN",
        display_name="档案管理员",
    )
    assert result["created_school"] and result["created_user"]
    assert len(result["password"]) >= 20 and result["password"] != "password123"
    user = await test_db.scalar(select(User).where(User.username == "admin01"))
    assert user is not None and user.display_name == "档案管理员" and user.status == "active"
    assert user.must_change_password is False and user.account_type == "general"
    assert verify_password(result["password"], user.password_hash)
    school = await test_db.scalar(select(School).where(School.code == "441701001001"))
    assert school is not None and school.name == "阳江一中"
    role_rows = await test_db.scalar(
        select(func.count()).select_from(UserRole).where(UserRole.user_id == user.id, UserRole.school_id == school.id)
    )
    assert role_rows == 1


@pytest.mark.asyncio
async def test_provision_reuses_existing_account_and_only_resets_when_asked(test_db):
    first = await provision(test_db, school_code="441701001001", school_name="阳江一中", username="viewer01", role_code="SCHOOL_VIEWER")
    user = await test_db.scalar(select(User).where(User.username == "viewer01"))
    original_hash = user.password_hash

    again = await provision(test_db, school_code="441701001001", school_name="别的名字", username="viewer01", role_code="SCHOOL_VIEWER")
    assert again["created_school"] is False and again["created_user"] is False
    assert again["password"] == ""
    assert (await test_db.scalar(select(User).where(User.username == "viewer01"))).password_hash == original_hash
    assert (await test_db.scalar(select(School).where(School.code == "441701001001"))).name == "阳江一中"
    assert await test_db.scalar(select(func.count()).select_from(User).where(User.username == "viewer01")) == 1

    rotated = await provision(
        test_db, school_code="441701001001", username="viewer01", role_code="SCHOOL_VIEWER", reset_password=True, must_change_password=True
    )
    refreshed = await test_db.scalar(select(User).where(User.username == "viewer01"))
    assert rotated["password"] and verify_password(rotated["password"], refreshed.password_hash)
    assert refreshed.password_hash != original_hash and refreshed.must_change_password is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values, message",
    [
        ({"school_code": "441701001001", "username": "school_admin_demo", "role_code": "SCHOOL_ADMIN"}, "示例账号"),
        ({"school_code": "DEMO_SCHOOL", "username": "admin01", "role_code": "SCHOOL_ADMIN"}, "demo_school"),
        ({"school_code": "441701001001", "username": "admin01", "role_code": "SCHOOL_ADMIN", "password": "password123"}, "默认密码"),
        ({"school_code": "441701001001", "username": "admin01", "role_code": "STUDENT"}, "不支持的角色"),
    ],
)
async def test_provision_rejects_identities_the_login_gate_would_block(test_db, values, message):
    before = await test_db.scalar(select(func.count()).select_from(User))
    with pytest.raises(ValueError, match=message):
        await provision(test_db, **values)
    assert await test_db.scalar(select(func.count()).select_from(User)) == before
    assert await test_db.scalar(select(func.count()).select_from(School).where(School.code.in_(["441701001001", "DEMO_SCHOOL"]))) == 0
