"""
Trace & Audit单元测试
"""
import pytest
from uuid import uuid4
from decimal import Decimal

from app.core.trace import (
    AgentRunTracer,
    ToolCallTracer,
    ModelUsageTracer,
    AuditLogger
)
from app.schemas.trace import (
    AgentRunCreate,
    AgentRunUpdate,
    ToolCallLogCreate,
    ModelUsageLogCreate,
    AuditLogCreate
)


@pytest.mark.asyncio
async def test_agent_run_lifecycle(test_db, sample_student_id, sample_school_id):
    """测试Agent运行生命周期"""
    tracer = AgentRunTracer(test_db)

    # 开始运行
    run_data = AgentRunCreate(
        school_id=sample_school_id,
        student_id=sample_student_id,
        query="我这次考得怎样？",
        intent="exam_summary",
        entitlement_level="BASIC"
    )
    run_id = await tracer.start_run(run_data)
    assert run_id is not None

    # 获取运行
    run = await tracer.get_run(run_id)
    assert run is not None
    assert run.status == "running"
    assert run.query == "我这次考得怎样？"

    # 完成运行
    update_data = AgentRunUpdate(
        status="success",
        tool_call_count=2,
        latency_ms=1500,
        input_tokens=100,
        output_tokens=200,
        estimated_cost=Decimal("0.003")
    )
    await tracer.finish_run(run_id, update_data)

    # 验证更新
    updated_run = await tracer.get_run(run_id)
    assert updated_run.status == "success"
    assert updated_run.tool_call_count == 2
    assert updated_run.finished_at is not None


@pytest.mark.asyncio
async def test_tool_call_logging(test_db, sample_student_id, sample_school_id):
    """测试Tool调用日志"""
    run_tracer = AgentRunTracer(test_db)
    tool_tracer = ToolCallTracer(test_db)

    # 创建运行
    run_data = AgentRunCreate(
        school_id=sample_school_id,
        student_id=sample_student_id,
        query="数学考了多少分？",
        entitlement_level="BASIC"
    )
    run_id = await run_tracer.start_run(run_data)

    # 记录Tool调用
    tool_log_data = ToolCallLogCreate(
        agent_run_id=run_id,
        tool_name="get_subject_scores",
        input_json={"subject": "数学"},
        output_summary_json={"score": 95, "rank": 5},
        status="success",
        latency_ms=250
    )
    log_id = await tool_tracer.log_tool_call(tool_log_data)
    assert log_id is not None

    # 获取Tool调用列表
    tool_calls = await tool_tracer.get_tool_calls(run_id)
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "get_subject_scores"
    assert tool_calls[0].status == "success"


@pytest.mark.asyncio
async def test_model_usage_logging(test_db, sample_student_id, sample_school_id):
    """测试模型使用日志"""
    run_tracer = AgentRunTracer(test_db)
    usage_tracer = ModelUsageTracer(test_db)

    # 创建运行
    run_data = AgentRunCreate(
        school_id=sample_school_id,
        student_id=sample_student_id,
        query="测试查询",
        entitlement_level="BASIC"
    )
    run_id = await run_tracer.start_run(run_data)

    # 记录模型使用
    usage_data = ModelUsageLogCreate(
        agent_run_id=run_id,
        provider="deepseek",
        model="deepseek-chat",
        prompt_tokens=150,
        completion_tokens=80,
        total_tokens=230,
        estimated_cost=Decimal("0.0023"),
        latency_ms=1200
    )
    log_id = await usage_tracer.log_usage(usage_data)
    assert log_id is not None


@pytest.mark.asyncio
async def test_audit_logging(test_db, sample_student_id):
    """测试审计日志"""
    audit_logger = AuditLogger(test_db)

    # 记录审计日志
    audit_data = AuditLogCreate(
        action="READ_DIAGNOSIS",
        actor_type="student",
        actor_id=sample_student_id,
        resource_type="diagnosis_report",
        resource_id=uuid4(),
        allowed=False,
        reason="ENTITLEMENT_REQUIRED"
    )
    log_id = await audit_logger.record(audit_data)
    assert log_id is not None

    # 查询审计日志
    logs = await audit_logger.list_logs(actor_id=sample_student_id)
    assert len(logs) == 1
    assert logs[0].action == "READ_DIAGNOSIS"
    assert logs[0].allowed == False


@pytest.mark.asyncio
async def test_list_agent_runs(test_db, sample_student_id, sample_school_id):
    """测试列出Agent运行"""
    tracer = AgentRunTracer(test_db)

    # 创建多个运行
    for i in range(3):
        run_data = AgentRunCreate(
            school_id=sample_school_id,
            student_id=sample_student_id,
            query=f"查询{i+1}",
            entitlement_level="BASIC"
        )
        await tracer.start_run(run_data)

    # 列出运行
    runs = await tracer.list_runs(student_id=sample_student_id)
    assert len(runs) == 3


@pytest.mark.asyncio
async def test_agent_run_detail(test_db, sample_student_id, sample_school_id):
    """测试获取Agent运行详情（包含Tool调用）"""
    run_tracer = AgentRunTracer(test_db)
    tool_tracer = ToolCallTracer(test_db)

    # 创建运行
    run_data = AgentRunCreate(
        school_id=sample_school_id,
        student_id=sample_student_id,
        query="完整查询",
        entitlement_level="BASIC"
    )
    run_id = await run_tracer.start_run(run_data)

    # 添加Tool调用
    tool_log = ToolCallLogCreate(
        agent_run_id=run_id,
        tool_name="test_tool",
        input_json={"param": "value"},
        status="success"
    )
    await tool_tracer.log_tool_call(tool_log)

    # 获取详情
    detail = await run_tracer.get_run_detail(run_id)
    assert detail is not None
    assert len(detail.tool_calls) == 1
    assert detail.tool_calls[0].tool_name == "test_tool"
