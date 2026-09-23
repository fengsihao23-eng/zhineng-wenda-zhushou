"""Bootstrap only the isolated local roster database; credentials stay in .local/."""
import asyncio
import json
import os
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4
from sqlalchemy import select
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.db.models import School, User, Role, UserRole

ROOT = Path(__file__).resolve().parents[3]
STATE = ROOT / ".local" / "yjyz-roster" / "identity.json"


async def main():
    if settings.DATABASE_URL != "postgresql+asyncpg://qa_education@127.0.0.1:55449/yjyz_roster_20260922":
        raise RuntimeError("This bootstrap requires the dedicated yjyz_roster_20260922 database")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.parent.chmod(0o700)
    stored = json.loads(STATE.read_text()) if STATE.exists() else {
        "username": "roster_operator_0922", "password": token_urlsafe(32),
        "bootstrap_path": "/preview/" + token_urlsafe(32),
        "jwt_secret": token_urlsafe(48), "app_secret": token_urlsafe(48),
    }
    async with AsyncSessionLocal() as db:
        school = await db.scalar(select(School).where(School.code == "441701004001"))
        if school is None:
            school = School(id=uuid4(), code="441701004001", external_school_id="441701004001", name="阳江一中", source_system="roster_excel")
            db.add(school)
            await db.flush()
        role = await db.scalar(select(Role).where(Role.code == "SCHOOL_ADMIN"))
        if role is None:
            role = Role(id=uuid4(), code="SCHOOL_ADMIN", name="学校管理员")
            db.add(role)
            await db.flush()
        user = await db.scalar(select(User).where(User.school_id == school.id, User.username == stored["username"], User.account_type == "general"))
        if user is None:
            user = User(id=uuid4(), school_id=school.id, username=stored["username"], account_type="general", password_hash=get_password_hash(stored["password"]), display_name="阳江一中 · 档案接入管理员")
            db.add(user)
            await db.flush()
            db.add(UserRole(user_id=user.id, school_id=school.id, role_id=role.id))
        await db.commit()
        stored.update(school_id=str(school.id), user_id=str(user.id))
    with os.fdopen(os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
        json.dump(stored, handle, ensure_ascii=False)
    print("Isolated school preview identity ready (credentials suppressed).")


if __name__ == "__main__":
    asyncio.run(main())
