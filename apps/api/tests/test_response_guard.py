"""
ResponseGuard单元测试
"""
import pytest
from app.core.response_guard import ResponseGuard
from app.schemas.guard import GuardConfig


@pytest.mark.asyncio
async def test_basic_forbidden_words(mock_student_context):
    """测试BASIC敏感词检查"""
    guard = ResponseGuard()

    answer = "你函数概念薄弱，基础不扎实"
    result = await guard.validate(
        answer=answer,
        context=mock_student_context,
        entitlement="BASIC"
    )

    assert result.ok == False
    assert any("薄弱" in issue for issue in result.issues)
    assert result.action in ["block", "warn"]


@pytest.mark.asyncio
async def test_number_accuracy(mock_student_context):
    """测试数字准确性检查"""
    guard = ResponseGuard()

    # Context中有520分，答案说525分（不在context中）
    answer = "你这次考了525分"
    result = await guard.validate(
        answer=answer,
        context=mock_student_context,
        entitlement="BASIC"
    )

    # 应该检测到数字不在context中
    assert any("525" in issue for issue in result.issues)


@pytest.mark.asyncio
async def test_valid_answer_passes(mock_student_context):
    """测试合规答案通过"""
    guard = ResponseGuard()

    answer = "你这次考试总分520分，班级排名第15名。"
    result = await guard.validate(
        answer=answer,
        context=mock_student_context,
        entitlement="BASIC"
    )

    assert result.ok == True
    assert result.action == "pass"


@pytest.mark.asyncio
async def test_privacy_check(mock_student_context):
    """测试隐私检查"""
    guard = ResponseGuard()

    # 提及其他学生
    answer = "你考了520分，李四同学考了530分。"
    result = await guard.validate(
        answer=answer,
        context=mock_student_context,
        entitlement="BASIC"
    )

    # 应该检测到其他学生信息
    assert any("李四" in issue for issue in result.issues)


@pytest.mark.asyncio
async def test_logic_consistency(mock_student_context):
    """测试逻辑一致性"""
    guard = ResponseGuard()

    # 矛盾的表述
    answer = "你的排名进步了，但同时也退步了。"
    result = await guard.validate(
        answer=answer,
        context=mock_student_context,
        entitlement="BASIC"
    )

    assert any("矛盾" in issue for issue in result.issues)


@pytest.mark.asyncio
async def test_custom_config():
    """测试自定义配置"""
    config = GuardConfig(
        check_numbers=False,
        forbidden_words=["自定义禁词"]
    )
    guard = ResponseGuard(config)

    assert guard.config.check_numbers == False
    assert "自定义禁词" in guard.config.forbidden_words


@pytest.mark.asyncio
async def test_diagnosis_user_allowed_words(mock_student_context):
    """测试DIAGNOSIS用户可以使用诊断措辞"""
    guard = ResponseGuard()

    # 更新context为DIAGNOSIS
    mock_student_context.entitlement_level = "DIAGNOSIS"

    answer = "你的函数概念薄弱，建议加强基础训练。"
    result = await guard.validate(
        answer=answer,
        context=mock_student_context,
        entitlement="DIAGNOSIS"
    )

    # DIAGNOSIS用户不应该被禁用词阻止
    # 注意：当前实现DIAGNOSIS用户不检查禁用词
    # 如果未来添加检查，这个测试需要调整
    assert result.action != "block"


@pytest.mark.asyncio
async def test_tool_numbers_are_allowed(mock_student_context):
    guard = ResponseGuard()
    result = await guard.validate(
        answer="数学得分为135分。",
        context=mock_student_context,
        entitlement="BASIC",
        allowed_numbers={135.0},
    )
    assert result.ok is True
