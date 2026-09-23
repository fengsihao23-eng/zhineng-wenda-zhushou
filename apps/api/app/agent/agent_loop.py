"""第一阶段的单一 Agent 主链路。

路由和数据 Tool 是确定性的，模型只负责把已取得的数据整理成自然语言。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import StudentContext, StudentContextBuilder
from app.agent.intent_router import IntentRouter
from app.ai.gateway import ModelGateway
from app.core.response_guard import ResponseGuard
from app.core.prompt_registry import PromptRegistry
from app.core.config import settings
from app.db.models.agent import AgentRun, ModelUsageLog, ToolCallLog
from app.core.errors import NotFoundError
from app.tools.base import ToolContext, ToolResult
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentStep(BaseModel):
    step_number: int
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_result: Optional[dict] = None
    reasoning: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentResponse(BaseModel):
    agent_run_id: str
    final_answer: str
    steps: List[AgentStep] = Field(default_factory=list)
    total_tools_called: int = 0
    student_context: Optional[dict] = None
    sources: list[dict] = Field(default_factory=list)
    guard_action: str = "pass"


class AgentLoop:
    """单一、有限、可追踪的 Agent 执行器。"""

    MAX_TOOL_ROUNDS = 1

    def __init__(
        self,
        db: AsyncSession,
        tool_registry: ToolRegistry,
        model_gateway: ModelGateway,
        prompt_registry: PromptRegistry | None = None,
    ):
        self.db = db
        self.tool_registry = tool_registry
        self.model_gateway = model_gateway
        self.context_builder = StudentContextBuilder(db)
        self.intent_router = IntentRouter()
        self.response_guard = ResponseGuard()
        self.prompt_registry = prompt_registry or PromptRegistry(db)

    async def run(
        self,
        user_query: str,
        student_id: UUID,
        school_id: UUID,
        user_id: UUID,
        request_id: str,
        chat_history: List[dict] | None = None,
        session_id: UUID | None = None,
        selected_exam_id: UUID | None = None,
        selected_subject_name: str | None = None,
    ) -> AgentResponse:
        if len(user_query.strip()) == 0 or len(user_query) > 4000:
            raise ValueError("消息长度必须在1到4000个字符之间")

        run_id = uuid4()
        context = await self.context_builder.build_context(student_id, school_id, selected_exam_id)
        intent = self.intent_router.route(user_query)
        entities = self.intent_router.extract_entities(user_query)
        if selected_exam_id:
            entities['exam_id'] = str(selected_exam_id)
        if selected_subject_name:
            entities['subject_name'] = selected_subject_name
            context.selected_subject_name = selected_subject_name
            context.recent_exams = [{k:v for k,v in exam.items() if k in {'exam_id','exam_name','exam_date'}} for exam in context.recent_exams]
            context.latest_exam = context.recent_exams[0] if context.recent_exams else None
        tool_context = ToolContext(
            request_id=request_id,
            agent_run_id=str(run_id),
            user_id=user_id,
            school_id=school_id,
            student_id=student_id,
            entitlement_level=context.entitlement_level,
        )

        run_model = AgentRun(
            id=run_id,
            session_id=session_id,
            school_id=school_id,
            student_id=student_id,
            query=user_query,
            intent=intent.name,
            entitlement_level=context.entitlement_level,
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(run_model)
        await self.db.commit()

        steps: list[AgentStep] = []
        sources: list[dict] = []
        tool_results: list[ToolResult] = []
        tools_called = 0
        try:
            tool_names = list(intent.suggested_tools[:1])
            if selected_subject_name and tool_names == ['get_exam_summary']:
                tool_names = ['get_subject_scores']
            for tool_name in tool_names:
                tool = self.tool_registry.get(tool_name)
                if not tool:
                    continue
                args = self._tool_args(tool_name, entities)
                try:
                    result = await tool.execute(tool_context=tool_context, args=args)
                except Exception as exc:
                    # A denied/failed tool should be represented as tool data so
                    # the model can explain the limitation; it must not turn a
                    # valid chat request into an internal 500.
                    result = ToolResult(
                        ok=False,
                        data={},
                        error_code=getattr(exc, "code", "TOOL_EXECUTION_ERROR"),
                        error_message="当前请求无法访问该数据",
                    )
                tools_called += 1
                tool_results.append(result)
                sources.extend([item.model_dump() for item in result.evidence])
                steps.append(
                    AgentStep(
                        step_number=len(steps) + 1,
                        tool_name=tool_name,
                        tool_args=args,
                        tool_result=result.model_dump(),
                        reasoning=f"根据意图 {intent.name} 查询本人学习数据",
                    )
                )
                self.db.add(
                    ToolCallLog(
                        agent_run_id=run_id,
                        tool_name=tool_name,
                        input_json=args,
                        output_summary_json={"ok": result.ok, "data": result.data},
                        status="success" if result.ok else "failed",
                        error_code=result.error_code,
                    )
                )

            system_prompt, prompt_version = await self._get_system_prompt(context)
            messages = self._build_messages(
                context, user_query, chat_history or [], tool_results, system_prompt
            )
            # Persist the exact prompt version used for this run so traces are
            # reproducible even when the registry is later updated.
            run_model.prompt_version = prompt_version
            provider_name = settings.MODEL_PROVIDER.lower()
            if provider_name == "fake":
                model_name = "fake-model"
            elif provider_name == "deepseek":
                model_name = settings.DEEPSEEK_MODEL
            else:
                model_name = settings.DEFAULT_MODEL
            model_response = await self.model_gateway.chat(
                model=model_name,
                messages=messages,
                tools=None,
                temperature=0.2,
                max_tokens=settings.MAX_TOKENS,
                timeout=settings.AGENT_TIMEOUT_SECONDS,
                trace_context={"agent_run_id": str(run_id)},
            )
            answer = model_response.content or model_response.text or "暂时无法生成回答。"
            self.db.add(
                ModelUsageLog(
                    agent_run_id=run_id,
                    provider=model_response.provider,
                    model=model_response.model,
                    prompt_tokens=model_response.usage.prompt_tokens,
                    completion_tokens=model_response.usage.completion_tokens,
                    total_tokens=model_response.usage.total_tokens,
                    latency_ms=model_response.latency_ms,
                )
            )

            guard = await self.response_guard.validate(
                answer=answer,
                context=context,
                entitlement=context.entitlement_level,
                allowed_numbers=self._tool_numbers(tool_results),
            )
            if guard.action != "pass":
                logger.warning(
                    "response_guard_intervention",
                    extra={"action": guard.action, "issues": guard.issues, "agent_run_id": str(run_id)},
                )
            if guard.action == "block":
                answer = "这个回答包含无法确认或不适合直接展示的信息，请联系老师核实。"

            run_model.status = "completed"
            run_model.tool_call_count = tools_called
            run_model.guard_action = guard.action
            run_model.finished_at = datetime.now(timezone.utc)
            await self.db.commit()
            return AgentResponse(
                agent_run_id=str(run_id),
                final_answer=answer,
                steps=steps,
                total_tools_called=tools_called,
                student_context=self._context_to_dict(context),
                sources=sources,
                guard_action=guard.action,
            )
        except Exception:
            run_model.status = "failed"
            run_model.error_code = "AGENT_FAILED"
            run_model.finished_at = datetime.now(timezone.utc)
            await self.db.commit()
            logger.exception("agent run failed", extra={"agent_run_id": str(run_id)})
            raise

    async def run_stream(self, **kwargs) -> AsyncGenerator[dict, None]:
        """兼容旧调用方的事件生成器；正式 API 负责统一 SSE 格式。"""
        result = await self.run(**kwargs)
        yield {"event": "content_delta", "data": {"content": result.final_answer}}
        yield {
            "event": "message_end",
            "data": {
                "agent_run_id": result.agent_run_id,
                "total_tools_called": result.total_tools_called,
            },
        }
        yield {"event": "done", "data": {"agent_run_id": result.agent_run_id}}

    @staticmethod
    def _tool_args(tool_name: str, entities: dict) -> dict:
        args = {}
        if tool_name in {"get_score_trend", "get_subject_scores", "get_question_losses", "get_diagnosis", "get_rank_change"} and entities.get("subject_name"):
            args['subject_name'] = entities['subject_name']
        if entities.get('exam_id'):
            args['current_exam_id' if tool_name == 'get_rank_change' else 'exam_id'] = entities['exam_id']
        return args

    def _build_messages(
        self,
        context: StudentContext,
        user_query: str,
        history: list[dict],
        results: list[ToolResult],
        system_prompt: str | None = None,
    ) -> list[dict]:
        messages = [
            {
                "role": "system",
                "content": system_prompt or (
                    "你是学生成绩问答助手。只使用已提供的本人数据回答，不能编造数字；"
                    "如果数据不存在，要明确说明。\n" + context.to_prompt_context()
                ),
            }
        ]
        messages.extend(history[-6:])
        messages.append({"role": "user", "content": user_query})
        for result in results:
            messages.append(
                {
                    # Tools are executed deterministically before the model
                    # call. A plain system context message keeps the request
                    # valid for providers that require a matching assistant
                    # tool_call message for every ``role=tool`` item.
                    "role": "system",
                    "content": "[TOOL_RESULT] "
                    + json.dumps(
                        result.data if result.ok else {"error": result.error_code},
                        ensure_ascii=False,
                    ),
                }
            )
        return messages

    async def _get_system_prompt(self, context: StudentContext) -> tuple[str, str | None]:
        """Render the registry prompt, with a safe built-in fallback.

        A fresh deployment may not have run the prompt seed script yet.  Chat
        remains usable in that state while still using the versioned registry
        whenever a published prompt exists.
        """
        try:
            prompt = await self.prompt_registry.get("student_qa_system")
            return (
                await self.prompt_registry.render(
                    name="student_qa_system",
                    student_name=context.student_name,
                    school_name="当前学校",
                    entitlement_level=context.entitlement_level,
                    context=context.to_prompt_context(),
                ),
                f"student_qa_system:{prompt.version}",
            )
        except NotFoundError:
            logger.info("prompt_registry_default_missing_using_builtin")
            return (
                "你是学生成绩问答助手。只使用已提供的本人数据回答，不能编造数字；"
                "如果数据不存在，要明确说明。\n" + context.to_prompt_context(),
                None,
            )
        except Exception as exc:
            logger.error("prompt_registry_database_error", extra={"error": str(exc)})
            return (
                "你是学生成绩问答助手。只使用已提供的本人数据回答，不能编造数字；"
                "如果数据不存在，要明确说明。\n" + context.to_prompt_context(),
                None,
            )

    @staticmethod
    def _context_to_dict(context: StudentContext) -> dict:
        return {
            "student_id": str(context.student_id),
            "student_name": context.student_name,
            "entitlement_level": context.entitlement_level,
            "latest_exam": context.latest_exam,
            "recent_exams_count": len(context.recent_exams),
        }

    @staticmethod
    def _tool_numbers(results: list[ToolResult]) -> set[float]:
        """Collect numeric facts returned by deterministic data tools."""
        numbers: set[float] = set()

        def collect(value):
            if isinstance(value, bool):
                return
            if isinstance(value, (int, float)):
                numbers.add(float(value))
            elif isinstance(value, dict):
                for item in value.values():
                    collect(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    collect(item)

        for result in results:
            collect(result.data)
        return numbers
