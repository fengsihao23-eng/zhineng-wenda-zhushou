"""Authentication regressions using synthetic identities and isolated stores."""
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import secrets
import sys
from uuid import uuid4

from fastapi import HTTPException
from jose import jwt
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings, settings
from app.core.security import (
    commit_token_revocations,
    create_access_token,
    create_refresh_token,
    decode_token,
    ensure_account_environment,
    get_password_hash,
    revoke_token,
    validate_token,
)
from app.db.models.school import School
from app.db.models.security import TokenRevocation
from app.db.models.user import User


async def login_synthetic_user(client, test_db, sample_school_id):
    credential = secrets.token_urlsafe(24)
    user = User(
        id=uuid4(), school_id=sample_school_id,
        username=f"qa-auth-{uuid4()}", password_hash=get_password_hash(credential),
        display_name="Synthetic QA user", status="active",
    )
    test_db.add(user)
    await test_db.commit()
    response = await client.post("/api/v1/auth/login", json={"username": user.username, "password": credential})
    assert response.status_code == 200
    return user, response.json()


@pytest.mark.asyncio
async def test_login_refresh_logout_readback_and_repeated_submit(client, test_db, sample_school_id):
    user, login = await login_synthetic_user(client, test_db, sample_school_id)
    initial_access = login["access_token"]
    first_refresh = login["refresh_token"]
    current = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {initial_access}"})
    assert current.status_code == 200
    assert current.json()["user_id"] == str(user.id)

    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert rotated.status_code == 200
    tokens = rotated.json()
    assert tokens["refresh_token"] != first_refresh
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": initial_access})).status_code == 401

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    body = {"refresh_token": tokens["refresh_token"]}
    assert (await client.post("/api/v1/auth/logout", headers=headers, json=body)).status_code == 204
    assert (await client.post("/api/v1/auth/logout", headers=headers, json=body)).status_code == 204
    # Read through fresh authorization, including access issued BEFORE refresh.
    for access in (initial_access, tokens["access_token"]):
        assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json=body)).status_code == 401
    assert await test_db.scalar(select(func.count()).select_from(TokenRevocation)) == 4


@pytest.mark.asyncio
async def test_logout_refresh_only_revokes_all_session_credentials(client, test_db, sample_school_id):
    _, login = await login_synthetic_user(client, test_db, sample_school_id)
    assert (await client.post("/api/v1/auth/logout", json={"refresh_token": login["refresh_token"]})).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"})).status_code == 401


@pytest.mark.asyncio
async def test_logout_rejects_missing_invalid_and_other_user_credentials(client, test_db, sample_school_id):
    _, first = await login_synthetic_user(client, test_db, sample_school_id)
    _, second = await login_synthetic_user(client, test_db, sample_school_id)
    assert (await client.post("/api/v1/auth/logout")).status_code == 401
    assert (await client.post("/api/v1/auth/logout", json={"refresh_token": "not-a-credential"})).status_code == 401
    response = await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {first['access_token']}"}, json={"refresh_token": second["refresh_token"]})
    assert response.status_code == 403
    for pair in (first, second):
        assert await validate_token(pair["access_token"], test_db, expected_type="access")
        assert await validate_token(pair["refresh_token"], test_db, expected_type="refresh")


@pytest.mark.asyncio
async def test_expired_and_legacy_tokens_cannot_authenticate(client, test_db):
    expired = create_access_token({"sub": str(uuid4())}, expires_delta=timedelta(seconds=-10))
    assert not await validate_token(expired, test_db, expected_type="access")
    # Expired, signed logout can be retried safely without re-enabling access.
    assert (await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {expired}"})).status_code == 204
    claims = decode_token(create_access_token({"sub": str(uuid4())}))
    claims.pop("sid")
    legacy = jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    assert not decode_token(legacy)


@pytest.mark.asyncio
async def test_revocation_store_failure_is_fail_closed(test_db, monkeypatch):
    token = create_refresh_token({"sub": str(uuid4())})

    async def failure(*args, **kwargs):
        raise OperationalError("synthetic storage failure", {}, None)

    monkeypatch.setattr(test_db, "scalar", failure)
    with pytest.raises(HTTPException) as error:
        await validate_token(token, test_db, expected_type="refresh")
    assert error.value.status_code == 503
    assert error.value.headers["X-Error-Code"] == "TOKEN_REVOCATION_UNAVAILABLE"
    monkeypatch.setattr(test_db, "execute", failure)
    with pytest.raises(HTTPException) as error:
        await revoke_token(token, test_db, expected_type="refresh")
    assert error.value.status_code == 503
    monkeypatch.setattr(test_db, "commit", failure)
    with pytest.raises(HTTPException) as error:
        await commit_token_revocations(test_db)
    assert error.value.status_code == 503


_WORKER = r"""
import asyncio, json, sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.core.security import validate_token, revoke_token, commit_token_revocations
from app.api.v1.endpoints.auth import RefreshRequest, refresh_token
from fastapi import HTTPException
async def run():
    request = json.load(sys.stdin)
    engine = create_async_engine(request['database_url'])
    async with AsyncSession(engine) as db:
        if request['action'] == 'read':
            result = bool(await validate_token(request['token'], db, expected_type=request['type']))
        elif request['action'] == 'refresh':
            try:
                await refresh_token(RefreshRequest(refresh_token=request['token']), db)
                result = 200
            except HTTPException as exc:
                result = exc.status_code
        else:
            result = await revoke_token(request['token'], db, expected_type=request['type'])
            await commit_token_revocations(db)
    await engine.dispose()
    print(json.dumps(result))
asyncio.run(run())
"""


async def token_worker(tmp_path, secret, **request):
    # A fresh working directory prevents Settings from discovering any .env.
    api_dir = Path(__file__).resolve().parents[1]
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", _WORKER,
        cwd=tmp_path,
        env={"PYTHONPATH": str(api_dir), "APP_ENV": "test", "DATABASE_URL": request["database_url"], "JWT_SECRET_KEY": secret, "LOG_FILE": str(tmp_path / "worker.log")},
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    output, _ = await process.communicate(json.dumps(request).encode())
    assert process.returncode == 0, "isolated authentication worker failed"
    return json.loads(output)


@pytest.mark.asyncio
async def test_persistent_revocation_survives_worker_restart(tmp_path, monkeypatch):
    secret = secrets.token_urlsafe(48)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", secret)
    url = f"sqlite+aiosqlite:///{tmp_path / 'revocation.sqlite'}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(TokenRevocation.__table__.create)
    token = create_access_token({"sub": str(uuid4())})
    request = {"database_url": url, "token": token, "type": "access"}
    assert await token_worker(tmp_path, secret, action="read", **request) is True
    assert await token_worker(tmp_path, secret, action="revoke", **request) is True
    # Each call launches then exits an independent Python process.
    assert await token_worker(tmp_path, secret, action="read", **request) is False
    assert await token_worker(tmp_path, secret, action="revoke", **request) is False
    async with AsyncSession(engine) as db:
        rows = (await db.scalars(select(TokenRevocation))).all()
        assert len(rows) == 1
        assert len(rows[0].token_id_hash) == 64
        assert token not in rows[0].token_id_hash
    await engine.dispose()


@pytest.mark.asyncio
async def test_two_process_refresh_race_has_one_winner(tmp_path, monkeypatch):
    from app.db.base import Base
    secret = secrets.token_urlsafe(48)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", secret)
    url = f"sqlite+aiosqlite:///{tmp_path / 'refresh.sqlite'}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    school_id, user_id = uuid4(), uuid4()
    async with AsyncSession(engine) as db:
        db.add(School(id=school_id, name="Synthetic school", code=f"QA-{school_id}"))
        db.add(User(id=user_id, school_id=school_id, username=f"qa-{user_id}", password_hash="unused", status="active"))
        await db.commit()
    token = create_refresh_token({"sub": str(user_id), "school_id": str(school_id)})
    request = {"database_url": url, "token": token, "type": "refresh", "action": "refresh"}
    results = await asyncio.gather(token_worker(tmp_path, secret, **request), token_worker(tmp_path, secret, **request))
    assert sorted(results) == [200, 401]
    assert await token_worker(tmp_path, secret, **request) == 401
    await engine.dispose()


@pytest.mark.asyncio
async def test_production_blocks_demo_names_school_and_renamed_default_password(client, test_db, sample_school_id, monkeypatch):
    formal, login = await login_synthetic_user(client, test_db, sample_school_id)
    demo_user = User(id=uuid4(), school_id=sample_school_id, username="teacher_demo", password_hash=get_password_hash(secrets.token_urlsafe(24)), status="active")
    renamed_demo = User(id=uuid4(), school_id=sample_school_id, username=f"renamed-{uuid4()}", password_hash=get_password_hash("password123"), status="active")
    test_db.add_all([demo_user, renamed_demo])
    await test_db.commit()
    demo_access = create_access_token({"sub": str(demo_user.id)})
    demo_refresh = create_refresh_token({"sub": str(demo_user.id)})
    monkeypatch.setattr(settings, "APP_ENV", "production")
    # Production never trusts a flag override to enable demo identities.
    monkeypatch.setattr(settings, "ENABLE_TEST_ACCOUNTS", True)
    assert settings.demo_accounts_allowed is False
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {demo_access}"})).status_code == 403
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": demo_refresh})).status_code == 403
    for user in (demo_user, renamed_demo):
        with pytest.raises(HTTPException) as error:
            await ensure_account_environment(user, test_db)
        assert error.value.status_code == 403
    await ensure_account_environment(formal, test_db)
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"})).status_code == 200
    school = await test_db.get(School, sample_school_id)
    school.code = "DEMO_SCHOOL"
    await test_db.commit()
    with pytest.raises(HTTPException):
        await ensure_account_environment(formal, test_db)


@pytest.mark.parametrize("environment", ["production", "staging", "prod"])
def test_production_configuration_forbids_demo_override(environment):
    config = Settings(_env_file=None, APP_ENV=environment, ENABLE_TEST_ACCOUNTS=True, SECRET_KEY=secrets.token_urlsafe(48), JWT_SECRET_KEY=secrets.token_urlsafe(48))
    assert config.ENABLE_TEST_ACCOUNTS is False
    with pytest.raises(RuntimeError):
        config.require_demo_environment()
