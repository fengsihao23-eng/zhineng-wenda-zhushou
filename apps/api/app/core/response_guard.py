"""
Response Guard - 答案校验和质量检查
"""
import re
from typing import Optional

from app.schemas.guard import GuardResult, GuardConfig
from app.agent.context import StudentContext


class ResponseGuard:
    """响应守卫 - 验证答案的合规性和准确性"""

    def __init__(self, config: Optional[GuardConfig] = None):
        self.config = config or GuardConfig()

    async def validate(
        self,
        answer: str,
        context: StudentContext,
        entitlement: str,
        allowed_numbers: set[float] | None = None,
    ) -> GuardResult:
        """
        验证答案

        Args:
            answer: 模型生成的答案
            context: 学生上下文
            entitlement: 权益等级

        Returns:
            GuardResult: 验证结果
        """
        issues = []

        # 1. 数字准确性检查
        if self.config.check_numbers:
            issues.extend(self._check_numbers(answer, context, allowed_numbers))

        # 2. 权益边界检查
        if entitlement == "BASIC" and self.config.check_basic_boundary:
            issues.extend(self._check_basic_boundary(answer))
        elif entitlement == "DIAGNOSIS":
            # DIAGNOSIS用户暂不做特殊检查，后续可添加
            pass

        # 3. 隐私保护检查
        if self.config.check_privacy:
            issues.extend(self._check_privacy(answer, context))

        # 4. 逻辑一致性检查
        if self.config.check_logic:
            issues.extend(self._check_logic_consistency(answer))

        # 决定处理动作
        action = self._decide_action(issues)

        return GuardResult(
            ok=len(issues) == 0,
            issues=issues,
            action=action
        )

    def _check_numbers(
        self,
        answer: str,
        context: StudentContext,
        allowed_numbers: set[float] | None = None,
    ) -> list[str]:
        """
        检查答案中的数字是否来自Context

        Args:
            answer: 答案
            context: 上下文

        Returns:
            问题列表
        """
        issues = []

        # 提取答案中的数字（允许单科和多科总分）
        answer_numbers = set()
        for match in re.finditer(r'(?<!\d)(\d+(?:\.\d+)?)\s*分', answer):
            num = float(match.group(1))
            if 0 <= num <= 1000:
                answer_numbers.add(num)

        # 提取Context中的所有数字
        context_str = context.to_prompt_context()
        context_numbers = set()
        for match in re.finditer(r'(?<!\d)(\d+(?:\.\d+)?)', context_str):
            context_numbers.add(float(match.group(1)))
        # Tool results are authoritative data gathered for this exact query.
        # Include them so a correct subject/rank answer is not rejected just
        # because the compact student context omits that field.
        context_numbers.update(allowed_numbers or set())
        known_numbers = tuple(context_numbers)

        # 检查是否有数字不在Context中
        for num in answer_numbers:
            if num not in context_numbers:
                # 允许一些计算结果（如平均分、差值）有小的偏差
                is_simple_derived_value = any(
                    abs(num - abs(left - right)) < 0.5
                    for left in known_numbers
                    for right in known_numbers
                )
                if not any(abs(num - ctx_num) < 0.5 for ctx_num in context_numbers) and not is_simple_derived_value:
                    issues.append(f"数字{num}不在Context中，可能是模型捏造")

        return issues

    def _check_basic_boundary(self, answer: str) -> list[str]:
        """
        检查BASIC用户是否出现诊断性措辞

        Args:
            answer: 答案

        Returns:
            问题列表
        """
        issues = []

        for word in self.config.forbidden_words:
            if word in answer:
                issues.append(f"BASIC用户不应出现诊断性措辞: '{word}'")

        return issues

    def _check_privacy(self, answer: str, context: StudentContext) -> list[str]:
        """
        检查是否泄漏其他学生信息

        Args:
            answer: 答案
            context: 上下文

        Returns:
            问题列表
        """
        issues = []

        # 提取答案中可能的人名（简单的中文姓名模式）
        # Only treat an explicit person label as a possible other-student
        # reference. Matching every two-to-four Chinese characters flags
        # ordinary exam names such as "学年第1次月考" as privacy leaks.
        name_pattern = r'([一-龥]{2,4})(?:同学|学生)'
        names = re.findall(name_pattern, answer)

        current_student_name = context.student_name
        for name in names:
            # 清理"同学"、"学生"等后缀
            clean_name = name.replace('同学', '').replace('学生', '')
            if clean_name != current_student_name and len(clean_name) >= 2:
                # 可能提及了其他学生
                issues.append(f"答案可能包含其他学生信息: '{name}'")

        return issues

    def _check_logic_consistency(self, answer: str) -> list[str]:
        """
        检查逻辑一致性

        Args:
            answer: 答案

        Returns:
            问题列表
        """
        issues = []

        # 检查矛盾的表述
        if "进步" in answer and "退步" in answer:
            issues.append("答案同时包含'进步'和'退步'，可能存在矛盾")

        if "上升" in answer and "下降" in answer:
            issues.append("答案同时包含'上升'和'下降'，可能存在矛盾")

        # 成绩总分可能是多科合计，允许城市试点使用的常见总分范围。
        score_matches = re.findall(r'(\d+)\s*分', answer)
        for score_str in score_matches:
            score = int(score_str)
            if score < 0 or score > 1000:
                issues.append(f"分数{score}超出合理范围(0-1000)")

        return issues

    def _decide_action(self, issues: list[str]) -> str:
        """
        根据问题严重程度决定处理动作

        Args:
            issues: 问题列表

        Returns:
            'pass' | 'warn' | 'block'
        """
        if not issues:
            return "pass"

        # 高危问题 - 必须阻断
        high_severity_keywords = ["其他学生", "捏造", "超出合理范围"]
        for issue in issues:
            if any(keyword in issue for keyword in high_severity_keywords):
                return "block"

        # 中危问题 - 警告但放行
        medium_severity_keywords = ["诊断性措辞", "矛盾"]
        for issue in issues:
            if any(keyword in issue for keyword in medium_severity_keywords):
                return "warn"

        # 默认警告
        return "warn"


class LightweightResponseGuard(ResponseGuard):
    """
    轻量级ResponseGuard（规则为主）
    继承自ResponseGuard，可以根据需要覆盖方法
    """
    pass
