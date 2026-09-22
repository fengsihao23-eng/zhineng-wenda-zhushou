"""Regressions for the 2026-09-16 review, using actual database/API responses."""
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event

from app.api.deps import AuthenticatedStudent, AuthenticatedUser, get_current_student, get_current_user
from app.db.models.exam import Exam, Subject
from app.db.models.platform import RiskEvent
from app.db.models.school import School
from app.db.models.score import StudentExamScore, StudentSubjectScore
from app.db.models.student import Student
from app.main import app


@pytest.fixture
def student_auth(sample_school_id, sample_student_id):
    current = AuthenticatedStudent(
        user_id=uuid4(), school_id=sample_school_id, student_id=sample_student_id,
        student_name="测试学生", roles=["STUDENT"],
    )
    app.dependency_overrides[get_current_student] = lambda: current
    yield current
    app.dependency_overrides.pop(get_current_student, None)


@pytest.mark.parametrize("full_score", [None, 0, -10])
async def test_dashboard_and_trends_use_complete_count_latest_twenty_and_valid_denominators(
    client, test_db, student_auth, full_score,
):
    school_id, student_id = student_auth.school_id, student_auth.student_id
    subjects = [Subject(id=uuid4(), school_id=school_id, code=f"S{i}", name=f"科目{i:02}") for i in range(11)]
    exams = [
        Exam(id=uuid4(), school_id=school_id, name=f"考试{i:02}", exam_type="monthly", start_date=date(2026, 1, 1) + timedelta(days=i))
        for i in range(25)
    ]
    # Another student's newest score must not affect the history or total.
    other_student = Student(id=uuid4(), school_id=school_id, name="其他学生", student_no="OTHER")
    test_db.add_all([*subjects, *exams, other_student])
    await test_db.flush()
    test_db.add(StudentExamScore(school_id=school_id, student_id=other_student.id, exam_id=exams[-1].id, total_score=749, full_score=750))
    for i, exam in enumerate(exams):
        test_db.add(StudentExamScore(
            school_id=school_id, student_id=student_id, exam_id=exam.id,
            total_score=500 + i, full_score=full_score if i == 24 else 750,
            class_rank=25 - i, grade_rank=125 - i,
        ))
        for j, subject in enumerate(subjects):
            points, maximum = ((120, 150) if j == 0 else (90, 100) if j == 1 else (10, full_score or 0) if j == 10 else (0, 100) if j == 9 else (70, 100))
            test_db.add(StudentSubjectScore(
                school_id=school_id, student_id=student_id, exam_id=exam.id,
                subject_id=subject.id, score=points, full_score=maximum,
            ))
    await test_db.commit()

    response = await client.get("/api/v1/platform/student/dashboard")
    assert response.status_code == 200
    dashboard = response.json()
    assert dashboard["exam_count"] == 25
    assert dashboard["latest_exam"]["name"] == "考试24"
    assert dashboard["latest_exam"]["total_score"] == 524
    assert dashboard["latest_exam"]["score_delta"] == 1
    assert dashboard["latest_exam"]["class_rank"] == 1
    assert dashboard["latest_exam"]["full_score"] is None
    assert [item["name"] for item in dashboard["subjects"][:2]] == ["科目01", "科目00"]
    assert [item["percentage"] for item in dashboard["subjects"][:2]] == [90, 80]
    assert dashboard["subjects"][-2]["percentage"] == 0
    assert dashboard["subjects"][-1]["name"] == "科目10"
    assert dashboard["subjects"][-1]["percentage"] is None
    assert dashboard["subjects"][-1]["full_score"] is None

    response = await client.get("/api/v1/platform/student/trends")
    assert response.status_code == 200
    trends = response.json()
    expected_exams = [f"考试{i:02}" for i in range(5, 25)]
    assert [item["name"] for item in trends["exams"]] == expected_exams
    assert trends["exams"][-1]["score"] == 524
    assert trends["exams"][-1]["full_score"] is None
    # Eleven subjects must all retain the same latest 20 exams (>200 rows).
    assert len(trends["subjects"]) == 220
    for subject in subjects:
        assert [row["exam"] for row in trends["subjects"] if row["subject"] == subject.name] == expected_exams


@pytest.mark.parametrize("method,path,status,code", [
    ("GET", "/api/v1/no-such-resource", 404, "RESOURCE_NOT_FOUND"),
    ("POST", "/api/health", 405, "METHOD_NOT_ALLOWED"),
])
async def test_framework_errors_match_business_error_contract(client, method, path, status, code):
    response = await client.request(method, path)
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["X-Error-Code"] == code
    assert isinstance(error["details"], dict)
    assert error["message"] in {"请求的资源不存在", "请求方法不被支持"}
    if status == 405:
        assert "GET" in response.headers["Allow"]


@pytest.mark.parametrize("size", [1, 50])
async def test_management_lists_have_constant_query_count_and_correct_aggregates(
    client, test_db, test_engine, sample_school_id, sample_student_id, size,
):
    pairs = [(sample_school_id, sample_student_id)]
    for i in range(1, size):
        school_id, student_id = uuid4(), uuid4()
        test_db.add(School(id=school_id, name=f"学校{i:02}", code=f"CODE-{i}"))
        await test_db.flush()
        test_db.add(Student(id=student_id, school_id=school_id, name=f"学生{i:02}", student_no=f"STUDENT-{i}"))
        pairs.append((school_id, student_id))
    await test_db.flush()
    for school_id, student_id in pairs:
        for i in range(2):
            exam = Exam(id=uuid4(), school_id=school_id, name=f"考试{i}", exam_type="monthly", start_date=date(2026, 1, i + 1))
            test_db.add(exam)
            await test_db.flush()
            test_db.add(StudentExamScore(school_id=school_id, student_id=student_id, exam_id=exam.id, total_score=500 + i, full_score=750))
        for status in ("open", "acknowledged", "closed"):
            test_db.add(RiskEvent(school_id=school_id, student_id=student_id, event_type="learning", title="测试", detail="测试", status=status))
    await test_db.commit()
    current = AuthenticatedUser(user_id=uuid4(), school_id=sample_school_id, username="city", roles=["CITY_OPERATOR"])
    app.dependency_overrides[get_current_user] = lambda: current
    selects = []

    def record_select(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(test_engine.sync_engine, "before_cursor_execute", record_select)
    try:
        response = await client.get("/api/v1/platform/management/students")
        assert response.status_code == 200
        assert len(selects) == 3
        assert len(response.json()) == size
        for row in response.json():
            assert row["latest_score"] == 501
            assert row["latest_exam"] == "考试1"
            assert row["open_risks"] == 2
        selects.clear()
        response = await client.get("/api/v1/platform/management/schools")
        assert response.status_code == 200
        assert len(selects) == 3
        assert len(response.json()) == size
        for row in response.json():
            assert row["students"] == 1
            assert row["open_risks"] == 2
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record_select)
        app.dependency_overrides.pop(get_current_user, None)
