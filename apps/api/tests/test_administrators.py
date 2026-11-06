"""Super-admin creation, authorization and lifecycle regressions."""
import hashlib
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


def creation(governance, **changes):
    return {'username': '01234567', 'password': '1', 'display_name': '新管理员',
            'school_id': str(governance['school_id']), 'roles': ['SCHOOL_ADMIN'],
            'must_change_password': False, **changes}


async def create(client, governance, **changes):
    response = await client.post(ROOT, headers=governance['headers']['SUPER_ADMIN'], json=creation(governance, **changes))
    assert response.status_code == 201, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


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
async def test_direct_creation_grants_school_immediately_and_isolates_tenant(client, test_db, governance):
    created = await create(client, governance, phone=' 13800000001 ', display_name=' 新管理员 ')
    user = await test_db.get(User, UUID(created['id']))
    assert user.school_id == governance['school_id'] and user.status == 'active'
    assert user.username == user.administrator_code == '01234567'
    assert user.password_hash != '1' and user.phone == '13800000001'
    assert created['roles'] == ['SCHOOL_ADMIN'] and created['display_name'] == '新管理员'
    assert await test_db.scalar(select(func.count()).select_from(UserRole).where(UserRole.user_id == user.id)) == 1
    headers = await login(client)
    assert (await client.post('/api/v1/auth/login', json={'username': '01234567', 'password': 'incorrect'})).status_code == 401
    for path in (ROOT, ROOT + '/history', '/api/v1/platform/management/schools'):
        assert (await client.get(path, headers=headers)).status_code == 403
    students = await client.get('/api/v1/platform/management/students', headers=headers)
    assert students.status_code == 200 and students.json() == []
    legacy = await client.get('/api/v1/admin/traces/audit', headers=headers)
    assert legacy.status_code == 200, legacy.text
    assert not any(row['action'].startswith('administrator.') for row in legacy.json())
    history = await client.get(ROOT + '/history', headers=governance['headers']['SUPER_ADMIN'], params={'administrator_id': created['id']})
    rows = history.json()['items']
    assert {'administrator.create', 'administrator.login'}.issubset(row['action'] for row in rows)
    recorded = next(row for row in rows if row['action'] == 'administrator.create')
    assert recorded['actor_username'] == governance['users']['SUPER_ADMIN'].username
    assert recorded['details']['after']['roles'] == ['SCHOOL_ADMIN'] and recorded['school_name'] == '另一所学校'
    assert any(row['action'] == 'administrator.request' and not row['allowed'] for row in rows)
    assert 'password_hash' not in history.text and '"password"' not in history.text


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['SCHOOL_ADMIN', 'EXAM_ADMIN', 'SCHOOL_VIEWER', 'QA'])
async def test_creation_uses_exactly_the_selected_permission(client, governance, role):
    created = await create(client, governance, roles=[role])
    assert created['roles'] == [role]
    await login(client)


@pytest.mark.asyncio
async def test_unique_eight_digit_accounts_and_validation_are_atomic(client, test_db, governance):
    headers = governance['headers']['SUPER_ADMIN']
    for changes in ({'roles': ['SUPER_ADMIN']}, {'roles': ['CITY_OPERATOR']}, {'roles': []},
                    {'roles': ['SCHOOL_ADMIN', 'EXAM_ADMIN']}, {'status': 'pending'}, {'registration_key': 'old-key'},
                    {'display_name': '   '}, {'password': ''}):
        response = await client.post(ROOT, headers=headers, json=creation(governance, **changes))
        assert response.status_code == 422, response.text
    for username in ('1234567', '123456789', 'abcdefgh', '13800138000'):
        assert (await client.post(ROOT, headers=headers, json=creation(governance, username=username))).status_code == 422
    assert await test_db.scalar(select(func.count(User.id)).where(User.administrator_code.is_not(None))) == 0
    await create(client, governance)
    duplicate = await client.post(ROOT, headers=headers, json=creation(governance, school_id=str(governance['users']['SUPER_ADMIN'].school_id)))
    assert duplicate.status_code == 409
    generated = await create(client, governance, username='')
    assert len(generated['username']) == 8 and generated['username'].isdigit() and generated['username'] != '01234567'
    assert await test_db.scalar(select(func.count(User.id)).where(User.administrator_code.is_not(None))) == 2


@pytest.mark.asyncio
async def test_unavailable_school_and_unconfigured_role_create_nothing(client, test_db, governance):
    school = await test_db.get(School, governance['school_id'])
    school.status = 'disabled'
    role = await test_db.scalar(select(Role).where(Role.code == 'QA'))
    role.code = 'RETIRED_QA'
    await test_db.commit()
    for changes, expected in (({'school_id': str(uuid4())}, 404), ({}, 404),
                              ({'school_id': str(governance['users']['SUPER_ADMIN'].school_id), 'roles': ['QA']}, 503)):
        response = await client.post(ROOT, headers=governance['headers']['SUPER_ADMIN'], json=creation(governance, **changes))
        assert response.status_code == expected, response.text
    assert await test_db.scalar(select(func.count(User.id)).where(User.administrator_code.is_not(None))) == 0
    assert await test_db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == 'administrator.create')) == 0


@pytest.mark.asyncio
async def test_public_registration_and_key_issuance_are_closed_even_with_valid_legacy_key(client, test_db, governance):
    key = 'synthetic-existing-key'
    row = AdministratorInvitation(id=uuid4(), label='历史密钥', key_hash=hashlib.sha256(key.encode()).hexdigest(),
        status='active', created_by=governance['users']['SUPER_ADMIN'].id, expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    test_db.add(row)
    await test_db.commit()
    response = await client.post(REGISTER, json={'registration_key': key, 'username': '01234567', 'password': '1', 'display_name': '新管理员'})
    assert response.status_code == 410 and key not in response.text
    headers = governance['headers']['SUPER_ADMIN']
    assert (await client.post(ROOT + '/invitations', headers=headers, json={'label': '停用密钥'})).status_code == 410
    listing = await client.get(ROOT + '/invitations', headers=headers)
    assert listing.status_code == 200 and listing.json()['total'] == 1
    assert key not in listing.text and 'key_hash' not in listing.text
    assert (await client.post(ROOT + f'/invitations/{row.id}/revoke', headers=headers)).status_code == 200
    assert await test_db.scalar(select(func.count(User.id)).where(User.administrator_code.is_not(None))) == 0


@pytest.mark.asyncio
async def test_creation_defaults_to_first_login_password_change(client, governance):
    payload = creation(governance)
    payload.pop('must_change_password')
    created = await client.post(ROOT, headers=governance['headers']['SUPER_ADMIN'], json=payload)
    assert created.status_code == 201 and created.json()['must_change_password']
    headers = await login(client)
    assert (await client.get('/api/v1/platform/management/students', headers=headers)).status_code == 403
    changed = await client.post('/api/v1/auth/change-password', headers=headers, json={'current_password': '1', 'new_password': '2'})
    assert changed.status_code == 200, changed.text
    assert (await client.get('/api/v1/platform/management/students', headers=await login(client, password='2'))).status_code == 200


@pytest.mark.asyncio
async def test_grant_change_conflict_disable_and_before_after_history(client, governance):
    created = await create(client, governance)
    first = await account(client, governance, created['id'])
    assigned = await authorize(client, governance, first, role='EXAM_ADMIN')
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
    created = await create(client, governance, password=long_password)
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
    owner = governance['users']['SUPER_ADMIN']
    assert (await client.post(ROOT, json=creation(governance))).status_code == 401
    for role in ('SCHOOL_ADMIN', 'CITY_OPERATOR', 'STUDENT', 'EXAM_ADMIN', 'SCHOOL_VIEWER', 'QA'):
        headers = governance['headers'][role]
        assert (await client.post(ROOT, headers=headers, json=creation(governance))).status_code == 403
        for path in (ROOT, ROOT + '/schools', ROOT + '/invitations', ROOT + '/history'):
            assert (await client.get(path, headers=headers)).status_code == 403
        assert (await client.post(ROOT + '/invitations', headers=headers, json={'label': '非法'})).status_code == 403
        assert (await client.post(ROOT + f'/{owner.id}/reset-password', headers=headers, json={'new_password': '1', 'expected_revision': owner.password_version})).status_code == 403
    listing = await client.get(ROOT, headers=governance['headers']['SUPER_ADMIN'], params={'scope': 'all'})
    assert listing.status_code == 422
    listing = await client.get(ROOT, headers=governance['headers']['SUPER_ADMIN'])
    assert listing.status_code == 200
    assert str(governance['users']['STUDENT'].id) not in {row['id'] for row in listing.json()['items']}
    assert 'password_hash' not in listing.text
    student = governance['users']['STUDENT']
    response = await client.post(ROOT + f'/{student.id}/reset-password', headers=governance['headers']['SUPER_ADMIN'],
        json={'new_password': 'forbidden-reset', 'expected_revision': student.password_version})
    assert response.status_code == 404
    history = await client.get(ROOT + '/history', headers=governance['headers']['SUPER_ADMIN'], params={'administrator_id': str(student.id)})
    assert history.status_code == 404
    assert (await client.get(ROOT + '/history')).status_code == 401
    protected = await authorize(client, governance, await account(client, governance, str(owner.id)), status='disabled')
    assert protected.status_code == 403


@pytest.mark.asyncio
async def test_history_pagination_and_secret_redaction(client, test_db, governance):
    headers = governance['headers']['SUPER_ADMIN']
    listing = await client.get(ROOT + '/invitations', headers=headers)
    assert listing.status_code == 200
    assert 'key_hash' not in listing.text
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
async def test_administrator_history_does_not_expose_school_business_payloads(client, test_db, governance):
    school_admin = governance['users']['SCHOOL_ADMIN']
    test_db.add(AuditLog(actor_id=school_admin.id, actor_type='user', action='student.data.export', allowed=True,
        reason='private student note', extra_data={'school_id': str(school_admin.school_id), 'score': 88,
            'scope': {'student_name': 'synthetic private name'}, 'before': {'report': 'private report'}}))
    await test_db.commit()
    response = await client.get(ROOT + '/history', headers=governance['headers']['SUPER_ADMIN'],
        params={'administrator_id': str(school_admin.id), 'action': 'student.data.export'})
    assert response.status_code == 200
    row = response.json()['items'][0]
    assert row['details'] == {'school_id': str(school_admin.school_id)}
    assert row['reason'] is None


@pytest.mark.asyncio
async def test_concurrent_creation_has_one_winner(client, test_db, test_engine, governance):
    if test_engine.dialect.name != 'postgresql':
        pytest.skip('Concurrent creation is verified against PostgreSQL uniqueness constraints')
    import asyncio
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.main import app
    from app.core.database import get_db
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
            results = await asyncio.gather(*[connection.post(ROOT, headers=governance['headers']['SUPER_ADMIN'], json=creation(governance)) for _ in range(2)])
        assert sorted(result.status_code for result in results) == [201, 409]
        assert await test_db.scalar(select(func.count(User.id)).where(User.administrator_code == '01234567')) == 1
        identifier = UUID(next(result.json()['id'] for result in results if result.status_code == 201))
        assert await test_db.scalar(select(func.count(UserRole.user_id)).where(UserRole.user_id == identifier)) == 1
        assert await test_db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == 'administrator.create')) == 1
    finally:
        app.dependency_overrides[get_db] = previous
