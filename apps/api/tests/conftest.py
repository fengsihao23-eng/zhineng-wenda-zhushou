"""
测试配置和Fixtures
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from httpx import ASGITransport, AsyncClient
from typing import AsyncGenerator
import uuid
import os

from app.main import app
from app.db.base import Base
from app.db.models.school import School
from app.db.models.user import User
from app.db.models.student import Student
from app.core.database import get_db


# Use SQLite by default so unit/integration tests are runnable on a clean
# checkout.  CI can set TEST_DATABASE_URL to a PostgreSQL async URL to run the
# same suite against the production engine as well.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest_asyncio.fixture
async def test_engine():
    """创建测试引擎"""
    connect_args = {"check_same_thread": False} if TEST_DATABASE_URL.startswith("sqlite") else {}
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
        connect_args=connect_args,
    )

    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # 清理
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_engine, sample_student_id, sample_school_id) -> AsyncGenerator[AsyncSession, None]:
    """创建测试数据库会话"""
    async_session = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        user_id = uuid.uuid4()
        session.add(School(id=sample_school_id, name="测试学校", code=f"TEST-{sample_school_id}"))
        session.add(User(
            id=user_id,
            school_id=sample_school_id,
            username=f"test-{user_id}",
            password_hash="not-used",
            display_name="测试用户",
        ))
        await session.flush()
        session.add(Student(
            id=sample_student_id,
            school_id=sample_school_id,
            user_id=user_id,
            student_no=f"S-{sample_student_id}",
            name="测试学生",
        ))
        await session.commit()
        yield session


@pytest_asyncio.fixture
async def client(test_db, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    """创建测试客户端"""

    # 覆盖数据库依赖
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    # A test's requests must not consume another test's rate-limit quota.
    from app.core.rate_limit import RateLimiter
    from app.core.config import settings
    monkeypatch.setattr("app.main.rate_limiter", RateLimiter(settings.RATE_LIMIT_PER_MINUTE, settings.RATE_LIMIT_PER_HOUR))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    # 清理
    app.dependency_overrides.clear()


@pytest.fixture
def sample_student_id() -> uuid.UUID:
    """示例学生ID"""
    return uuid.uuid4()


@pytest.fixture
def sample_school_id() -> uuid.UUID:
    """示例学校ID"""
    return uuid.uuid4()


@pytest.fixture
def sample_exam_id() -> uuid.UUID:
    """示例考试ID"""
    return uuid.uuid4()


@pytest.fixture
def mock_student_context():
    """Mock学生上下文"""
    from app.agent.context import StudentContext

    return StudentContext(
        student_id=uuid.uuid4(),
        school_id=uuid.uuid4(),
        student_name="张三",
        entitlement_level="BASIC",
        recent_exams=[
            {
                "exam_id": str(uuid.uuid4()),
                "exam_name": "2024年期中考试",
                "total_score": 520,
                "class_rank": 15,
                "grade_rank": 89
            }
        ],
        latest_exam={
            "exam_id": str(uuid.uuid4()),
            "exam_name": "2024年期中考试",
            "total_score": 520,
            "class_rank": 15,
            "grade_rank": 89
        }
    )
