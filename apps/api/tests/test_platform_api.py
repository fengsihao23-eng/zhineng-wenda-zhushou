"""Contract tests for the student product and governance workflows."""
from uuid import uuid4

import pytest

from app.api.deps import AuthenticatedStudent, AuthenticatedUser, get_current_student, get_current_user
from app.main import app


@pytest.fixture
def auth_override(sample_school_id, sample_student_id):
    current = AuthenticatedStudent(
        user_id=uuid4(), school_id=sample_school_id, student_id=sample_student_id,
        student_name="测试学生", roles=["STUDENT"],
    )
    app.dependency_overrides[get_current_student] = lambda: current
    yield current
    app.dependency_overrides.pop(get_current_student, None)


@pytest.mark.asyncio
async def test_student_dashboard_and_parent_authorization(client, auth_override):
    dashboard = await client.get("/api/v1/platform/student/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["student"]["name"] == "测试学生"
    assert dashboard.json()["latest_exam"] is None

    created = await client.post(
        "/api/v1/platform/student/authorization",
        json={"parent_name": "测试家长", "parent_phone": "13800000000"},
    )
    assert created.status_code == 201
    authorization = created.json()
    assert authorization["status"] == "pending"

    approved = await client.post(
        f"/api/v1/platform/parent/authorizations/{authorization['id']}/approve",
        json={"share_code": authorization["share_code"]},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "active"


@pytest.mark.asyncio
async def test_knowledge_review_lifecycle(client, test_db, sample_school_id):
    management_user = AuthenticatedUser(
        user_id=uuid4(), school_id=sample_school_id, username="admin", roles=["SCHOOL_ADMIN"]
    )
    app.dependency_overrides[get_current_user] = lambda: management_user
    try:
        created = await client.post(
            "/api/v1/platform/management/knowledge",
            json={
                "title": "测试知识点",
                "subject": "数学",
                "doc_type": "讲义",
                "content": "定义域应先检查限制条件。",
                "source_name": "测试教研组",
                "source_reference": "测试讲义第 1 页",
            },
        )
        assert created.status_code == 201
        document_id = created.json()["id"]
        assert created.json()["status"] == "draft"

        submitted = await client.post(
            f"/api/v1/platform/management/knowledge/{document_id}/review",
            json={"action": "submit"},
        )
        assert submitted.status_code == 200
        assert submitted.json()["status"] == "pending_review"

        published = await client.post(
            f"/api/v1/platform/management/knowledge/{document_id}/review",
            json={"action": "approve"},
        )
        assert published.status_code == 200
        assert published.json()["status"] == "published"

        offline = await client.post(
            f"/api/v1/platform/management/knowledge/{document_id}/review",
            json={"action": "offline", "reason": "内容已更新"},
        )
        assert offline.status_code == 200
        assert offline.json()["status"] == "offline"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_management_endpoint_rejects_student(client, auth_override):
    current = AuthenticatedUser(
        user_id=auth_override.user_id,
        school_id=auth_override.school_id,
        username="student",
        roles=["STUDENT"],
    )
    app.dependency_overrides[get_current_user] = lambda: current
    try:
        response = await client.get("/api/v1/platform/management/overview")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "MANAGEMENT_ROLE_REQUIRED"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
