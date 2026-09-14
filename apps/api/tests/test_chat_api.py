"""Contract and tenant-scope tests for the student chat API."""

from uuid import uuid4

import pytest
from app.agent.agent_loop import AgentResponse
from app.api.deps import AuthenticatedStudent, get_current_student
from app.api.v1.endpoints import chat as chat_endpoint
from app.main import app


@pytest.fixture
def authenticated_student(sample_school_id, sample_student_id):
    return AuthenticatedStudent(
        user_id=uuid4(),
        school_id=sample_school_id,
        student_id=sample_student_id,
        student_name="测试学生",
        roles=["STUDENT"],
    )


@pytest.fixture
def fake_agent_result():
    return AgentResponse(
        agent_run_id=str(uuid4()),
        final_answer="根据你的学习数据：总分：520。",
        total_tools_called=1,
        sources=[{"kind": "exam", "id": "exam-1"}],
    )


@pytest.fixture
def auth_override(authenticated_student):
    app.dependency_overrides[get_current_student] = lambda: authenticated_student
    yield authenticated_student
    app.dependency_overrides.pop(get_current_student, None)


@pytest.mark.asyncio
async def test_chat_session_lifecycle(client, auth_override):
    created = await client.post("/api/v1/chat/sessions", json={"title": "期中复盘"})
    assert created.status_code == 201
    session = created.json()
    assert session["title"] == "期中复盘"
    assert session["status"] == "active"
    assert session["message_count"] == 0

    listed = await client.get("/api/v1/chat/sessions")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [session["id"]]

    archived = await client.delete(f"/api/v1/chat/sessions/{session['id']}")
    assert archived.status_code == 204
    assert (await client.get("/api/v1/chat/sessions")).json() == []


@pytest.mark.asyncio
async def test_chat_send_message_persists_contract(
    client, auth_override, fake_agent_result, monkeypatch
):
    async def fake_run_agent(*args, **kwargs):
        return fake_agent_result

    monkeypatch.setattr(chat_endpoint, "_run_agent", fake_run_agent)
    session = (await client.post("/api/v1/chat/sessions")).json()
    response = await client.post(
        f"/api/v1/chat/sessions/{session['id']}/messages",
        json={"content": "我这次考得怎样？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session["id"]
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"] == fake_agent_result.final_answer
    assert body["tools_called"] == 1
    assert body["sources"] == fake_agent_result.sources

    history = await client.get(f"/api/v1/chat/sessions/{session['id']}/messages")
    assert history.status_code == 200
    assert [item["role"] for item in history.json()] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_chat_client_message_id_is_idempotent(
    client, auth_override, fake_agent_result, monkeypatch
):
    calls = 0

    async def fake_run_agent(*args, **kwargs):
        nonlocal calls
        calls += 1
        return fake_agent_result

    monkeypatch.setattr(chat_endpoint, "_run_agent", fake_run_agent)
    session = (await client.post("/api/v1/chat/sessions")).json()
    client_message_id = str(uuid4())
    payload = {"content": "请总结我的成绩", "client_message_id": client_message_id}

    first = await client.post(f"/api/v1/chat/sessions/{session['id']}/messages", json=payload)
    second = await client.post(f"/api/v1/chat/sessions/{session['id']}/messages", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["message"]["id"] == first.json()["message"]["id"]
    assert calls == 1
    history = await client.get(f"/api/v1/chat/sessions/{session['id']}/messages")
    assert [item["role"] for item in history.json()] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_chat_stream_has_monotonic_sse_sequence(
    client, auth_override, fake_agent_result, monkeypatch
):
    async def fake_run_agent(*args, **kwargs):
        return fake_agent_result

    monkeypatch.setattr(chat_endpoint, "_run_agent", fake_run_agent)
    session = (await client.post("/api/v1/chat/sessions")).json()
    response = await client.post(
        f"/api/v1/chat/sessions/{session['id']}/stream",
        json={"content": "请总结我的成绩"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [block for block in response.text.split("\n\n") if block.strip()]
    names = [next(line for line in block.splitlines() if line.startswith("event: "))[7:] for block in events]
    sequences = [int(next(line for line in block.splitlines() if '"seq":' in line).split('"seq":', 1)[1].split(',', 1)[0]) for block in events]
    assert names[0] == "message_start"
    assert names[-2:] == ["message_end", "done"]
    assert sequences == list(range(1, len(sequences) + 1))


@pytest.mark.asyncio
async def test_client_message_id_replays_completed_assistant(
    client, auth_override, fake_agent_result, monkeypatch
):
    calls = 0

    async def fake_run_agent(*args, **kwargs):
        nonlocal calls
        calls += 1
        return fake_agent_result

    monkeypatch.setattr(chat_endpoint, "_run_agent", fake_run_agent)
    session = (await client.post("/api/v1/chat/sessions")).json()
    payload = {"content": "请总结我的成绩", "client_message_id": str(uuid4())}
    first = await client.post(f"/api/v1/chat/sessions/{session['id']}/messages", json=payload)
    second = await client.post(f"/api/v1/chat/sessions/{session['id']}/messages", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.json()["message"]["id"] == second.json()["message"]["id"]
    assert calls == 1


@pytest.mark.asyncio
async def test_chat_session_cannot_cross_school_scope(client, auth_override):
    foreign_session_id = uuid4()
    response = await client.get(f"/api/v1/chat/sessions/{foreign_session_id}/messages")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"
