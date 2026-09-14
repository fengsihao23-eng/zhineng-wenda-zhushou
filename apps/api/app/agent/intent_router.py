"""
Intent Router - 意图识别
"""
import re
from typing import Optional, List
from pydantic import BaseModel


class Intent(BaseModel):
    """意图"""
    name: str
    confidence: float
    suggested_tools: List[str] = []
    reasoning: str = ""


class IntentRouter:
    """意图路由器 - 规则+模型混合"""

    # 规则匹配模式
    PATTERNS = {
        "exam_summary": [
            r"这次.*?考.*?怎.*?样",
            r"考.*?了.*?多少分",
            r"最近.*?考试.*?成绩",
            r"总分.*?多少",
            r"考.*?得.*?如何",
        ],
        "subject_scores": [
            r"(语文|数学|英语|物理|化学|生物|历史|地理|政治).*?多少分",
            r"各科.*?成绩",
            r"科目.*?得分",
            r".*?科.*?考.*?怎么样",
        ],
        "ranking_change": [
            r"比.*?上次",
            r"进步.*?退步",
            r"排名.*?变化",
            r"名次.*?升.*?降",
            r".*?对比",
        ],
        "score_trend": [
            r"趋势",
            r"最近.*?次.*?考试",
            r"成绩.*?走势",
            r".*?变化.*?情况",
        ],
        "question_loss": [
            r"哪.*?题.*?丢分",
            r"哪.*?题.*?扣分",
            r"失分.*?最多",
            r"错.*?最多",
            r"薄弱.*?题目",
        ],
        "diagnosis": [
            r"诊断",
            r"分析.*?原因",
            r"知识点.*?薄弱",
            r"学习.*?建议",
            r"如何.*?提高",
        ],
    }

    # 意图到工具的映射
    INTENT_TO_TOOLS = {
        "exam_summary": ["get_exam_summary"],
        "subject_scores": ["get_subject_scores"],
        "ranking_change": ["get_rank_change"],
        "score_trend": ["get_score_trend"],
        "question_loss": ["get_question_losses"],
        "diagnosis": ["get_diagnosis"],
    }

    def __init__(self):
        pass

    def route(self, user_query: str) -> Intent:
        """
        识别用户意图
        Returns: Intent对象
        """
        user_query_lower = user_query.lower()

        # 规则匹配
        matched_intents = []

        for intent_name, patterns in self.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, user_query):
                    matched_intents.append(intent_name)
                    break

        # 根据匹配结果返回意图
        if not matched_intents:
            return Intent(
                name="general_chat",
                confidence=0.5,
                suggested_tools=[],
                reasoning="无明确意图，使用通用对话"
            )

        # 如果有多个意图，选择第一个（优先级由顺序决定）
        primary_intent = matched_intents[0]
        suggested_tools = self.INTENT_TO_TOOLS.get(primary_intent, [])

        return Intent(
            name=primary_intent,
            confidence=1.0 if len(matched_intents) == 1 else 0.8,
            suggested_tools=suggested_tools,
            reasoning=f"规则匹配到意图: {primary_intent}"
        )

    def extract_entities(self, user_query: str) -> dict:
        """
        从用户查询中提取实体（科目名、考试ID等）
        """
        entities = {}

        # 提取科目名称
        subjects = ["语文", "数学", "英语", "物理", "化学", "生物", "历史", "地理", "政治"]
        for subject in subjects:
            if subject in user_query:
                entities["subject_name"] = subject
                break

        # 提取考试相关实体
        if "上次" in user_query or "上一次" in user_query:
            entities["exam_reference"] = "previous"
        elif "这次" in user_query or "本次" in user_query:
            entities["exam_reference"] = "current"
        elif "最近" in user_query:
            entities["exam_reference"] = "recent"

        return entities
