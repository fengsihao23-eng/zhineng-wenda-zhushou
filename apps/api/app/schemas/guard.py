"""
Response Guard Schemas
"""
from pydantic import BaseModel, Field


class GuardResult(BaseModel):
    """Guard验证结果"""
    ok: bool = Field(..., description="是否通过验证")
    issues: list[str] = Field(default_factory=list, description="发现的问题")
    action: str = Field(..., description="处理动作: pass/warn/block")
    corrected_answer: str | None = Field(None, description="修正后的答案")


class GuardConfig(BaseModel):
    """Guard配置"""
    check_numbers: bool = Field(default=True, description="检查数字准确性")
    check_basic_boundary: bool = Field(default=True, description="检查BASIC权益边界")
    check_privacy: bool = Field(default=True, description="检查隐私保护")
    check_logic: bool = Field(default=True, description="检查逻辑一致性")
    forbidden_words: list[str] = Field(
        default_factory=lambda: [
            "薄弱", "基础不扎实", "理解不够", "能力不足",
            "粗心", "学习习惯", "掌握不牢", "概念模糊"
        ],
        description="BASIC用户禁用词汇"
    )
