"""Synthetic administrator registration, authorization and lifecycle regressions."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from app.core.security import create_access_token, get_password_hash
from app.db.models.administrator import AdministratorInvitation
from app.db.models.school import School
from app.db.models.trace import AuditLog
from app.db.models.user import Role, User, UserRole

ROOT = '/api/v1/platform/administrators'
REGISTER = '/api/v1/auth/register-administrator'


@pytest_asyncio.fixture
async def governance(test_db, sample_school_id):
    school = School(id=uuid4(), name='另一所学校', code=f'OTHER-{uuid4()}', status='active')
    test_db.add(school)
    users, headers = {}, {}
    for code in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'CITY_OPERATOR', 'STUDENT', 'EXAM_ADMIN', 'SCHOOL_VIEWER', 'QA']:
        role = Role(id=uuid4(), code=code, name=code)
        user = User(id=uuid4(), school_id=sample_school_id, username=f'governance-{code}',
                    password_hash=get_password_hash('SyntheticPassword123'), display_name=code, status='active')
        test_db.add_all([role, user])
        await test_db.flush()
        test_db.add(UserRole(user_id=user.id, school_id=user.school_id, role_id=role.id))
        users[code] = user
        headers[code] = {'Authorization': f"Bearer {create_access_token({'sub': str(user.id), 'school_id': str(user.school_id)})}"}
    await test_db.commit()
    return {'users': users, 'headers': headers, 'school_id': school.id}


async def invite(client, governance):
    response = await client.post(ROOT + '/invitations', headers=governance['headers']['SUPER_ADMIN'], json={'label': '测试教务管理员'})
    assert response.status_code == 201, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


def registration(key, username='01234567', password='1'):
    return {'registration_key': key, 'username': username, 'password': password, 'display_name': '新管理员'}


async def pending(client, governance, password='1'):
    invitation = await invite(client, governance)
    response = await client.post(REGISTER, json=registration(invitation['registration_key'], password=password))
    assert response.status_code == 201, response.text
    return response.json(), invitation


async def account(client, governance, identifier):
    response = await client.get(ROOT, headers=governance['headers']['SUPER_ADMIN'])
    assert response.status_code == 200, response.text
    return next(row for row in response.json()['items'] if row['id'] == identifier)


async def authorize(client, governance, user, role='SCHOOL_ADMIN', **changes):
    payload = {'display_name': user['display_name'], 'phone': user['phone'] or '', 'status': 'active',
               'school_id': str(governance['school_id']), 'roles': [role], 'expected_revision': user['revision'], **changes}
    return await client.patch(ROOT + f"/{user['id']}", headers=governance['headers']['SUPER_ADMIN'], json=payload)


async def login(client, password='1'):
    response = await client.post('/api/v1/auth/login', json={'username': '01234567', 'password': password})
    assert response.status_code == 200, response.text
    return {'Authorization': f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_pending_registration_authorization_and_tenant_isolation(client, test_db, governance):
    created, invitation = await pending(client, governance)
    user = await test_db.get(User, UUID(created['id']))
    assert user.school_id is None and user.status == 'pending'
    assert user.username == user.administrator_code == '01234567'
    assert user.password_hash != '1' and user.phone is None
    assert created['roles'] == []
    assert await test_db.scalar(select(func.count()).select_from(UserRole).where(UserRole.user_id == user.id)) == 0
    blocked = await client.post('/api/v1/auth/login', json={'username': user.username, 'password': '1'})
    assert blocked.status_code == 403 and blocked.json()['error']['code'] == 'ADMIN_APPROVAL_PENDING'
    assigned = await authorize(client, governance, await account(client, governance, created['id']))
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()['roles'] == ['SCHOOL_ADMIN'] and assigned.json()['school_id'] == str(governance['school_id'])
    headers = await login(client)
    assert (await client.post('/api/v1/auth/login', json={'username': '01234567', 'password': 'incorrect'})).status_code == 401
    assert (await client.get(ROOT + '/history', headers=headers)).status_code == 403
    assert (await client.get('/api/v1/platform/management/schools', headers=headers)).status_code == 403
    students = await client.get('/api/v1/platform/management/students', headers=headers)
    assert students.status_code == 200 and students.json() == []
    legacy = await client.get('/api/v1/admin/traces/audit', headers=headers)
    assert legacy.status_code == 200, legacy.text
    assert not any(row['action'].startswith('administrator.') for row in legacy.json())
    history = await client.get(ROOT + '/history', headers=governance['headers']['SUPER_ADMIN'], params={'administrator_id': created['id']})
    assert history.status_code == 200, history.text
    rows = history.json()['items']
    assert {'administrator.register', 'administrator.update', 'administrator.login'}.issubset(row['action'] for row in rows)
    assert any(row['action'] == 'administrator.request' and not row['allowed'] for row in rows)
    assert any(row['action'] == 'administrator.login' and not row['allowed'] for row in rows)
    assert invitation['registration_key'] not in history.text


@pytest.mark.asyncio
async def test_single_use_no_self_grant_unique_eight_digit_accounts(client, test_db, governance):
    invitation = await invite(client, governance)
    payload = registration(invitation['registration_key'])
    for extra in ({'roles': ['SUPER_ADMIN']}, {'school_id': str(governance['school_id'])}, {'status': 'active'}):
        response = await client.post(REGISTER, json={**payload, **extra})
        assert response.status_code == 422 and invitation['registration_key'] not in response.text
    for username in ('1234567', '123456789', 'abcdefgh', '13800138000'):
        assert (await client.post(REGISTER, json={**payload, 'username': username})).status_code == 422
    assert (await client.post(REGISTER, json=registration('wrong-secret'))).status_code == 400
    assert (await client.post(REGISTER, json=payload)).status_code == 201
    assert (await client.post(REGISTER, json={**payload, 'username': '88888888'})).status_code == 400
    stored = await test_db.get(AdministratorInvitation, UUID(invitation['id']))
    await test_db.refresh(stored)
    assert stored.status == 'used' and stored.used_by is not None
    assert invitation['registration_key'] not in stored.key_hash
    another = await invite(client, governance)
    assert (await client.post(REGISTER, json=registration(another['registration_key']))).status_code == 409
    random_account = await client.post(REGISTER, json=registration(another['registration_key'], ''))
    assert random_account.status_code == 201
    assert len(random_account.json()['username']) == 8 and random_account.json()['username'].isdigit()


@pytest.mark.asyncio
async def test_expired_revoked_invites_do_not_create_accounts(client, test_db, governance):
    for state in ('expired', 'revoked'):
        invitation = await invite(client, governance)
        row = await test_db.get(AdministratorInvitation, UUID(invitation['id']))
        if state == 'expired':
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
            await test_db.commit()
        else:
            result = await client.post(ROOT + f'/invitations/{row.id}/revoke', headers=governance['headers']['SUPER_ADMIN'])
            assert result.status_code == 200
        assert (await client.post(REGISTER, json=registration(invitation['registration_key']))).status_code == 400
    assert await test_db.scalar(select(func.count(User.id)).where(User.administrator_code.is_not(None))) == 0


@pytest.mark.asyncio
async def test_grant_change_conflict_disable_and_before_after_history(client, governance):
    created, _ = await pending(client, governance)
    first = await account(client, governance, created['id'])
    assigned = await authorize(client, governance, first)
    assert assigned.status_code == 200
    headers = await login(client)
    assert (await authorize(client, governance, first)).status_code == 409
    disabled = await authorize(client, governance, await account(client, governance, created['id']), status='disabled', display_name='已更新姓名')
    assert disabled.status_code == 200
    assert (await client.get('/api/v1/auth/me', headers=headers)).status_code == 403
    read_only = await authorize(client, governance, disabled.json(), role='SCHOOL_VIEWER')
    assert read_only.status_code == 200
    assert (await client.get('/api/v1/auth/me', headers=headers)).status_code == 401
    headers = await login(client)
    assert (await client.post(ROOT + '/invitations', headers=headers, json={'label': '非法'})).status_code == 403
    assert (await client.post('/api/v1/platform/education/school/subjects', headers=headers, json={'name': '不可写入'})).status_code == 403
    history = await client.get(ROOT + '/history', headers=governance['headers']['SUPER_ADMIN'], params={'administrator_id': created['id'], 'action': 'administrator.update', 'school_id': str(governance['school_id'])})
    assert history.status_code == 200, history.text
    assert history.json()['total'] == 3
    assert any(row['details']['before']['display_name'] == '新管理员' and row['details']['after']['display_name'] == '已更新姓名' for row in history.json()['items'])


@pytest.mark.asyncio
async def test_free_password_reset_invalidates_sessions_and_forced_change(client, governance):
    long_password = '自由密码' * 30
    created, _ = await pending(client, governance, password=long_password)
    assert (await authorize(client, governance, await account(client, governance, created['id']))).status_code == 200
    headers = await login(client, password=long_password)
    current = await account(client, governance, created['id'])
    reset = await client.post(ROOT + f"/{created['id']}/reset-password", headers=governance['headers']['SUPER_ADMIN'], json={
        'new_password': '2', 'expected_revision': current['revision'], 'must_change_password': True})
    assert reset.status_code == 200, reset.text
    assert (await client.get('/api/v1/auth/me', headers=headers)).status_code == 401
    assert (await client.post('/api/v1/auth/login', json={'username': '01234567', 'password': long_password})).status_code == 401
    headers = await login(client, password='2')
    assert (await client.get('/api/v1/platform/management/students', headers=headers)).status_code == 403
    changed = await client.post('/api/v1/auth/change-password', headers=headers, json={'current_password': '2', 'new_password': '3'})
    assert changed.status_code == 200, changed.text
    await login(client, password='3')
    history = await client.get(ROOT + '/history', headers=governance['headers']['SUPER_ADMIN'], params={'action': 'administrator.password.reset'})
    assert history.status_code == 200 and history.json()['total'] == 1
    assert 'new_password' not in history.text and 'password_hash' not in history.text


@pytest.mark.asyncio
async def test_super_admin_only_all_accounts_and_protection(client, governance):
    invitation = await invite(client, governance)
    owner = governance['users']['SUPER_ADMIN']
    for role in ('SCHOOL_ADMIN', 'CITY_OPERATOR', 'STUDENT', 'EXAM_ADMIN'):
        headers = governance['headers'][role]
        for path in (ROOT, ROOT + '/schools', ROOT + '/invitations', ROOT + '/history'):
            assert (await client.get(path, headers=headers)).status_code == 403
        assert (await client.post(ROOT + '/invitations', headers=headers, json={'label': '非法'})).status_code == 403
        assert (await client.post(ROOT + f"/invitations/{invitation['id']}/revoke", headers=headers)).status_code == 403
        assert (await client.post(ROOT + f'/{owner.id}/reset-password', headers=headers, json={'new_password': '1', 'expected_revision': owner.password_version})).status_code == 403
    listing = await client.get(ROOT, headers=governance['headers']['SUPER_ADMIN'], params={'scope': 'all'})
    assert listing.status_code == 200
    assert str(governance['users']['STUDENT'].id) in {row['id'] for row in listing.json()['items']}
    assert 'password_hash' not in listing.text
    assert (await client.get(ROOT + '/history')).status_code == 401
    protected = await authorize(client, governance, await account(client, governance, str(owner.id)), status='disabled')
    assert protected.status_code == 403


@pytest.mark.asyncio
async def test_history_pagination_and_secret_redaction(client, test_db, governance):
    invitation = await invite(client, governance)
    headers = governance['headers']['SUPER_ADMIN']
    listing = await client.get(ROOT + '/invitations', headers=headers)
    assert listing.status_code == 200
    assert invitation['registration_key'] not in listing.text and 'key_hash' not in listing.text
    owner = governance['users']['SUPER_ADMIN']
    for i in range(23):
        test_db.add(AuditLog(actor_id=owner.id, actor_type='user', action='test.historic.operation', allowed=True, extra_data={'sequence': i}))
    await test_db.commit()
    first = await client.get(ROOT + '/history', headers=headers, params={'action': 'test.historic.operation', 'page_size': 20})
    second = await client.get(ROOT + '/history', headers=headers, params={'action': 'test.historic.operation', 'page': 2})
    assert first.status_code == 200, first.text
    assert first.json()['total'] == 23 and len(first.json()['items']) == 20 and len(second.json()['items']) == 3
    assert not {row['id'] for row in first.json()['items']}.intersection(row['id'] for row in second.json()['items'])


@pytest.mark.asyncio
@pytest.mark.parametrize('shared_key', [True, False])
async def test_concurrent_registration_has_one_winner(client, test_db, test_engine, governance, shared_key):
    if test_engine.dialect.name != 'postgresql':
        pytest.skip('Concurrent registration is verified against PostgreSQL row locks')
    import asyncio
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.main import app
    from app.core.database import get_db
    first = await invite(client, governance)
    second = first if shared_key else await invite(client, governance)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    previous = app.dependency_overrides[get_db]

    async def independent_db():
        async with factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    app.dependency_overrides[get_db] = independent_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as connection:
            results = await asyncio.gather(*[connection.post(REGISTER, json=registration(item['registration_key'])) for item in (first, second)])
        assert sum(result.status_code == 201 for result in results) == 1
        assert all(result.status_code in (201, 400, 409) for result in results)
        assert await test_db.scalar(select(func.count(User.id)).where(User.administrator_code == '01234567')) == 1
        if not shared_key:
            assert await test_db.scalar(select(func.count(AdministratorInvitation.id)).where(AdministratorInvitation.status == 'active')) == 1
    finally:
        app.dependency_overrides[get_db] = previous
