"""Real workbook edge cases and Flash request contract; no live API credentials."""
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select
from app.core.config import settings
from app.ai.providers.deepseek import DeepSeekProvider
from app.ai.gateway import ModelGateway
from app.ai.schemas import Usage
from app.db.models import Subject, TeachingAssignment
from app.db.models.roster import TeacherProfile
from app.services.roster_excel import duty_codes
from test_education_workbench import actors, post, P  # noqa: F401
from test_roster_workflows import teacher, upload, confirm, classroom


@pytest.mark.asyncio
async def test_flash_request_uses_configured_model_and_disables_thinking(monkeypatch):
    monkeypatch.setattr(settings, 'DEEPSEEK_MODEL', 'deepseek-flash')
    monkeypatch.setattr(settings, 'DEEPSEEK_THINKING', 'disabled')
    provider = DeepSeekProvider('synthetic-key')
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='连接成功', tool_calls=None), finish_reason='stop')], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2, total_tokens=12), model='deepseek-flash')
    create = AsyncMock(return_value=response)
    monkeypatch.setattr(provider.client.chat.completions, 'create', create)
    try:
        answer = await provider.chat('', [{'role': 'user', 'content': '连接测试'}], max_tokens=32)
        assert answer.model == 'deepseek-flash'
        params = create.call_args.kwargs
        assert params['model'] == 'deepseek-flash'
        assert params['extra_body'] == {'thinking': {'type': 'disabled'}}
        assert params['max_tokens'] == 32
        assert ModelGateway._model_for_provider(provider, 'gpt-4o-mini') == 'deepseek-flash'
        assert provider.estimate_cost(Usage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000), 'deepseek-flash') == Decimal('0.0015')
    finally:
        await provider.client.close()


@pytest.mark.asyncio
async def test_multi_subject_leader_has_each_subject_and_only_selected_grade(client, test_db, actors):
    await classroom(client)
    english = Subject(school_id=actors['school'].id, code='EN', name='英语', source_system='native')
    test_db.add(english)
    await test_db.commit()
    await post(client, '/school/classes', {'external_class_id': '11.1', 'name': '高中二年级1班'})
    done = await confirm(client, await upload(client, [teacher('multi-leader', 教研组长负责年级科目='10.数学,10.英语', 说明='备课组长(高中一年级数学)\n备课组长(高中一年级英语)')]))
    identifier = UUID(done['report']['imported'][0]['id'])
    assignments = (await test_db.scalars(select(TeachingAssignment).where(TeachingAssignment.teacher_user_id == identifier))).all()
    assert len(assignments) == 2
    assert {a.subject_id for a in assignments} == {english.id, actors['subject'].id}
    assert 'SUBJECT_LEADER' in (await test_db.get(TeacherProfile, identifier)).duties


def test_imported_admin_roles_do_not_match_negated_titles():
    assert 'SCHOOL_ADMIN' in duty_codes({'说明': '学校管理员'})
    assert 'EXAM_ADMIN' in duty_codes({'说明': '考试管理员'})
    assert 'SCHOOL_ADMIN' not in duty_codes({'说明': '非学校管理员'})
    assert 'PRINCIPAL' not in duty_codes({'说明': '副校长'})


@pytest.mark.asyncio
async def test_exam_administrator_can_manage_exams_but_not_rosters(client, actors):
    from app.main import app
    from app.api.deps import get_current_user, AuthenticatedUser
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(actors['teacher'].id, actors['school'].id, 'exam-admin', ['TEACHER', 'EXAM_ADMIN'])
    assert (await client.get(P + '/school/subjects')).json()['total'] == 1
    exam = await post(client, '/school/exams', {'external_exam_id': 'scoped-exam', 'name': '权限测试考试', 'exam_type': 'test', 'start_date': '2026-09-22'})
    assert (await client.get(P + '/school/exams')).json()['total'] == 1
    assert (await client.get(P + f"/exams/{exam['id']}")).status_code == 200
    assert (await client.put(P + f"/exams/{exam['id']}/subjects", json={'subject_id': str(actors['subject'].id), 'full_score': 100})).status_code == 200
    assert (await client.get(P + '/roster/teachers/records')).status_code == 403
    assert (await client.get(P + '/school/teaching')).status_code == 403
    await post(client, '/school/classes', {'external_class_id': 'denied', 'name': '不允许'}, status=403)
