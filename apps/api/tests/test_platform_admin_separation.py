"""The in-place split must retain school identities, passwords, data and history."""
import json
import os
import stat
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.security import get_password_hash, verify_password
from app.db.models import Role, School, Student, User, UserRole
from app.db.models.trace import AuditLog
from scripts.separate_platform_admin import separate


@pytest_asyncio.fixture
async def split_setup(test_db, sample_school_id, sample_student_id):
    school = await test_db.get(School, sample_school_id)
    school.name, school.code = '示例学校', 'TEST-0001'
    student = await test_db.get(Student, sample_student_id)
    student.profile_fields = {'学校名称': '阳江高级中学', '学校编号': '441702004001'}
    roles = {code: Role(id=uuid4(), code=code, name=code) for code in ('SUPER_ADMIN', 'SCHOOL_ADMIN')}
    legacy = User(id=uuid4(), school_id=school.id, username='admin', account_type='general', status='active',
        password_hash=get_password_hash('OriginalSchoolPassword'), display_name='Original admin', must_change_password=False)
    test_db.add_all([*roles.values(), legacy])
    await test_db.flush()
    test_db.add_all(UserRole(user_id=legacy.id, school_id=school.id, role_id=role.id) for role in roles.values())
    test_db.add(AuditLog(id=uuid4(), actor_type='user', actor_id=legacy.id, action='historic.school.operation', allowed=True,
        extra_data={'note': 'Original history'}))
    await test_db.commit()
    return school, legacy, student


async def run_split(db, path, phase):
    return await separate(db, credential_file=path, expected_code='TEST-0001', school_name='阳江高级中学',
        school_code='441702004001', phase=phase)


@pytest.mark.asyncio
async def test_two_phase_split_preserves_old_login_and_school_relationships(test_db, split_setup, client, tmp_path):
    school, legacy, student = split_setup
    old_hash, old_version = legacy.password_hash, legacy.password_version
    ids = (school.id, legacy.id, student.id)
    initial_users = await test_db.scalar(select(func.count()).select_from(User))
    path = tmp_path / 'private-credentials.json'
    prepared = await run_split(test_db, path, 'prepare')
    assert prepared['school_admin_roles'] == ['SCHOOL_ADMIN', 'SUPER_ADMIN']
    assert prepared['created_platform_account']
    assert school.code == 'TEST-0001'
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    secret = json.loads(path.read_text())
    assert len(secret['username']) == 8 and secret['username'].isdigit()
    platform = await test_db.get(User, UUID(secret['super_admin_id']))
    assert verify_password(secret['initial_password'], platform.password_hash)
    assert not platform.must_change_password
    assert (await test_db.scalars(select(Role.code).join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == platform.id))).all() == ['SUPER_ADMIN']
    # Validate the actual login and governance endpoint before demoting admin.
    response = await client.post('/api/v1/auth/login', json={'username': secret['username'], 'password': secret['initial_password']})
    assert response.status_code == 200, response.text
    token = response.json()['access_token']
    assert (await client.get('/api/v1/platform/administrators', headers={'Authorization': 'Bearer ' + token})).status_code == 200
    assert (await client.get('/api/v1/platform/education/roster/students/records', headers={'Authorization': 'Bearer ' + token})).status_code == 403
    original_login = await client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'OriginalSchoolPassword'})
    assert original_login.status_code == 200
    original_token = original_login.json()['access_token']
    final = await run_split(test_db, path, 'finalize')
    assert final['school_admin_roles'] == ['SCHOOL_ADMIN']
    assert (school.name, school.code) == ('阳江高级中学', '441702004001')
    assert (school.id, legacy.id, student.id) == ids
    assert student.school_id == school.id == legacy.school_id
    assert legacy.password_hash == old_hash and legacy.password_version == old_version + 1
    assert not legacy.must_change_password and platform.must_change_password
    assert (await client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + token})).status_code == 401
    assert (await client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + original_token})).status_code == 401
    old_login = await client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'OriginalSchoolPassword'})
    assert old_login.status_code == 200 and old_login.json()['user']['roles'] == ['SCHOOL_ADMIN']
    assert await test_db.scalar(select(func.count()).select_from(User)) == initial_users + 1
    assert await test_db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'historic.school.operation')) == 1
    before = path.read_bytes()
    replay = await run_split(test_db, path, 'finalize')
    assert not replay['created_platform_account'] and path.read_bytes() == before
    assert await test_db.scalar(select(func.count()).select_from(User)) == initial_users + 1
    assert await test_db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'administrator.platform_access.remove')) == 1
    first = await client.post('/api/v1/auth/login', json={'username': secret['username'], 'password': secret['initial_password']})
    assert first.status_code == 200 and first.json()['user']['must_change_password']
    changed = await client.post('/api/v1/auth/change-password', headers={'Authorization': 'Bearer ' + first.json()['access_token']},
        json={'current_password': secret['initial_password'], 'new_password': 'ReplacementPlatformPassword'})
    assert changed.status_code == 200
    headers = {'Authorization': 'Bearer ' + changed.json()['access_token']}
    assert (await client.get('/api/v1/platform/administrators', headers=headers)).status_code == 200
    assert (await client.get('/api/v1/platform/education/roster/students/records', headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_finalization_requires_a_verified_independent_account(test_db, split_setup, tmp_path):
    path = tmp_path / 'credentials.json'
    with pytest.raises(ValueError, match='先创建独立超管'):
        await run_split(test_db, path, 'finalize')
    assert not path.exists()
    await run_split(test_db, path, 'prepare')
    with pytest.raises(ValueError, match='验证登录'):
        await run_split(test_db, path, 'finalize')
    assert split_setup[0].code == 'TEST-0001'


@pytest.mark.asyncio
async def test_conflicting_school_code_stops_before_creating_credentials(test_db, split_setup, tmp_path):
    other = School(id=uuid4(), name='Another school', code='441702004001')
    test_db.add(other)
    await test_db.commit()
    path = tmp_path / 'credentials.json'
    with pytest.raises(ValueError, match='已被其他学校使用'):
        await run_split(test_db, path, 'prepare')
    assert not path.exists() and split_setup[0].code == 'TEST-0001'
