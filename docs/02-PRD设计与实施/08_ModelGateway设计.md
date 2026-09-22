# PRD-08: Model Gateway 设计

---
Status: active
Owner: AI 平台
Last verified: 2026-09-11
Evidence: 目标 Provider/Gateway 契约；retry、fallback、usage 和超时能力须以集成测试与运行指标证明。
Supersedes: 旧版 Model Gateway 设计
---

> 本文是接口和治理目标，不代表当前模型供应商适配已经完成。

## 1. 概述

所有模型调用统一经过 ModelGateway。业务代码禁止直接调用模型 API。

### 1.1 为什么需要 Gateway

**问题**：
```python
# ❌ 业务代码到处都是
requests.post("https://xxx/v1/chat/completions", ...)
```

**解决**：
```python
# ✅ 统一入口
response = await model_gateway.chat(...)
```

**好处**：
- 统一 Provider 适配
- 统一熔断降级
- 统一 Token 统计
- 统一 Trace
- 统一 Cost 计算
- 可替换 Provider

---

## 2. ModelGateway 接口

### 2.1 核心接口

```python
class ModelGateway:
    """模型调用网关"""
    
    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: int = 30,
        trace_context: dict | None = None
    ) -> ModelResponse:
        """
        标准对话调用
        """
        pass
    
    async def stream(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: int = 30,
        trace_context: dict | None = None
    ) -> AsyncIterator[ModelChunk]:
        """
        流式对话调用（SSE）
        """
        pass
    
    async def structured(
        self,
        model: str,
        messages: list[dict],
        response_schema: dict,
        temperature: float = 0.1,
        timeout: int = 30,
        trace_context: dict | None = None
    ) -> dict:
        """
        结构化输出（JSON Schema）
        用于 Intent Router 等场景
        """
        pass
```

### 2.2 ModelResponse

```python
class ModelResponse(BaseModel):
    """模型响应"""
    text: str | None
    tool_calls: list[ToolCall] = []
    usage: Usage
    provider: str
    model: str
    latency_ms: int
    finish_reason: str
    raw_response_ref: str | None = None  # 调试用

class Usage(BaseModel):
    """Token 使用量"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ToolCall(BaseModel):
    """工具调用"""
    id: str
    name: str
    arguments: dict
```

---

## 3. Provider 设计

### 3.1 BaseProvider

```python
from abc import ABC, abstractmethod

class BaseProvider(ABC):
    """Provider 基类"""
    
    @abstractmethod
    async def chat(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> ModelResponse:
        """同步调用"""
        pass
    
    @abstractmethod
    async def stream(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> AsyncIterator[ModelChunk]:
        """流式调用"""
        pass
    
    @abstractmethod
    def normalize_response(self, raw_response: dict) -> ModelResponse:
        """标准化响应"""
        pass
    
    @abstractmethod
    def estimate_cost(self, usage: Usage, model: str) -> Decimal:
        """估算成本"""
        pass
```

### 3.2 OpenAI Compatible Provider

```python
class OpenAICompatibleProvider(BaseProvider):
    """
    OpenAI 兼容 Provider
    支持 OpenAI / DeepSeek / Qwen / 自建 vLLM 等
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: str,
        default_model: str,
        price_per_1k_input: Decimal,
        price_per_1k_output: Decimal
    ):
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key
        )
        self.default_model = default_model
        self.price_input = price_per_1k_input
        self.price_output = price_per_1k_output
    
    async def chat(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> ModelResponse:
        start = time.time()
        
        response = await self.client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            **kwargs
        )
        
        latency_ms = int((time.time() - start) * 1000)
        
        return self.normalize_response(response, latency_ms)
    
    def normalize_response(
        self,
        raw_response,
        latency_ms: int
    ) -> ModelResponse:
        """标准化为统一格式"""
        
        choice = raw_response.choices[0]
        message = choice.message
        
        # 提取 tool_calls
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments)
                ))
        
        return ModelResponse(
            text=message.content,
            tool_calls=tool_calls,
            usage=Usage(
                prompt_tokens=raw_response.usage.prompt_tokens,
                completion_tokens=raw_response.usage.completion_tokens,
                total_tokens=raw_response.usage.total_tokens
            ),
            provider=self.__class__.__name__,
            model=raw_response.model,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason
        )
    
    def estimate_cost(self, usage: Usage, model: str) -> Decimal:
        """估算成本"""
        input_cost = (usage.prompt_tokens / 1000) * self.price_input
        output_cost = (usage.completion_tokens / 1000) * self.price_output
        return input_cost + output_cost
```

### 3.3 DeepSeek Provider

```python
class DeepSeekProvider(OpenAICompatibleProvider):
    """DeepSeek 专用 Provider"""
    
    def __init__(self, api_key: str):
        super().__init__(
            base_url="https://api.deepseek.com/v1",
            api_key=api_key,
            default_model="deepseek-chat",
            price_per_1k_input=Decimal("0.0001"),  # 实际价格
            price_per_1k_output=Decimal("0.0002")
        )
```

### 3.4 Qwen Provider

```python
class QwenProvider(OpenAICompatibleProvider):
    """Qwen 专用 Provider"""
    
    def __init__(self, api_key: str):
        super().__init__(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=api_key,
            default_model="qwen-plus",
            price_per_1k_input=Decimal("0.0004"),
            price_per_1k_output=Decimal("0.0012")
        )
```

---

## 4. 模型路由策略

### 4.1 Router 配置

```python
class ModelRouter:
    """模型路由"""
    
    def __init__(self, config: dict):
        self.providers = {}
        self.routes = config["routes"]
        self.fallbacks = config["fallbacks"]
        
        # 初始化 Providers
        for name, cfg in config["providers"].items():
            self.providers[name] = self._create_provider(cfg)
    
    def select_model(
        self,
        task_type: str,
        entitlement: str,
        context_size: int
    ) -> tuple[str, BaseProvider]:
        """
        选择模型
        
        task_type: 'chat', 'intent', 'guard'
        entitlement: 'BASIC', 'DIAGNOSIS'
        context_size: 上下文大小（token）
        """
        
        # BASIC 用户：低成本模型
        if entitlement == "BASIC":
            if task_type == "chat":
                return "deepseek-chat", self.providers["deepseek"]
            elif task_type == "intent":
                return "gpt-4o-mini", self.providers["openai_mini"]
        
        # DIAGNOSIS 用户：按需升级
        else:
            if task_type == "chat":
                if context_size > 8000:
                    return "gpt-4o", self.providers["openai"]
                else:
                    return "deepseek-chat", self.providers["deepseek"]
        
        # 默认
        return self.routes.get("default", ("deepseek-chat", self.providers["deepseek"]))
```

### 4.2 路由示例配置

```yaml
providers:
  deepseek:
    type: openai_compatible
    base_url: https://api.deepseek.com/v1
    api_key: ${DEEPSEEK_API_KEY}
    model: deepseek-chat
    
  openai_mini:
    type: openai_compatible
    base_url: https://api.openai.com/v1
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o-mini
    
  openai:
    type: openai_compatible
    base_url: https://api.openai.com/v1
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o

routes:
  basic_chat: deepseek
  diagnosis_chat: deepseek
  intent_classification: openai_mini
  response_guard: openai_mini
  
fallbacks:
  deepseek: openai_mini
  openai: deepseek
```

---

## 5. Circuit Breaker / Retry

### 5.1 熔断器

```python
class CircuitBreaker:
    """熔断器"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60,
        half_open_timeout: int = 30
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.half_open_timeout = half_open_timeout
        
        self.failures = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open
    
    def call(self, func: Callable) -> Any:
        """执行调用"""
        
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half_open"
            else:
                raise CircuitBreakerOpenError()
        
        try:
            result = func()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        """成功"""
        self.failures = 0
        if self.state == "half_open":
            self.state = "closed"
    
    def _on_failure(self):
        """失败"""
        self.failures += 1
        self.last_failure_time = time.time()
        
        if self.failures >= self.failure_threshold:
            self.state = "open"
    
    def _should_attempt_reset(self) -> bool:
        """是否尝试重置"""
        return (
            time.time() - self.last_failure_time
        ) >= self.half_open_timeout
```

### 5.2 Retry 策略

```python
async def call_with_retry(
    self,
    func: Callable,
    max_retries: int = 2,
    backoff_factor: float = 2.0
) -> Any:
    """带重试的调用"""
    
    for attempt in range(max_retries + 1):
        try:
            return await func()
        
        except HTTPStatusError as e:
            # 429 / 5xx 可重试
            if e.response.status_code in [429, 500, 502, 503, 504]:
                if attempt < max_retries:
                    delay = backoff_factor ** attempt
                    logger.warning(f"Retry {attempt+1}/{max_retries} after {delay}s")
                    await asyncio.sleep(delay)
                    continue
            
            # 4xx 参数错误不重试
            raise
        
        except (asyncio.TimeoutError, ConnectionError) as e:
            if attempt < max_retries:
                delay = backoff_factor ** attempt
                await asyncio.sleep(delay)
                continue
            raise
    
    raise MaxRetriesExceededError()
```

---

## 6. ModelGateway 实现

### 6.1 完整实现

```python
class ModelGateway:
    def __init__(
        self,
        router: ModelRouter,
        circuit_breakers: dict[str, CircuitBreaker],
        usage_tracker: UsageTracker
    ):
        self.router = router
        self.circuit_breakers = circuit_breakers
        self.usage_tracker = usage_tracker
    
    async def chat(
        self,
        model: str | None = None,
        messages: list[dict],
        task_type: str = "chat",
        entitlement: str = "BASIC",
        **kwargs
    ) -> ModelResponse:
        """统一对话调用"""
        
        # 1. 路由选择
        if not model:
            context_size = self._estimate_context_size(messages)
            model, provider = self.router.select_model(
                task_type=task_type,
                entitlement=entitlement,
                context_size=context_size
            )
        else:
            provider = self.router.get_provider_for_model(model)
        
        # 2. 熔断检查
        breaker = self.circuit_breakers.get(provider.name)
        if breaker and breaker.state == "open":
            # 降级到 fallback
            fallback_provider = self.router.get_fallback(provider.name)
            if fallback_provider:
                logger.warning(f"Circuit open, fallback to {fallback_provider.name}")
                provider = fallback_provider
            else:
                raise CircuitBreakerOpenError()
        
        # 3. 带重试调用
        response = await self.call_with_retry(
            lambda: provider.chat(model, messages, **kwargs)
        )
        
        # 4. 统计
        await self.usage_tracker.record(
            provider=provider.name,
            model=model,
            usage=response.usage,
            cost=provider.estimate_cost(response.usage, model),
            latency_ms=response.latency_ms
        )
        
        return response
```

---

## 7. Usage Tracking

### 7.1 使用量统计

```python
class UsageTracker:
    """使用量追踪"""
    
    async def record(
        self,
        provider: str,
        model: str,
        usage: Usage,
        cost: Decimal,
        latency_ms: int,
        trace_context: dict | None = None
    ):
        """记录使用"""
        
        await self.db.execute(
            insert(ModelUsageLog).values(
                provider=provider,
                model=model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                estimated_cost=cost,
                latency_ms=latency_ms,
                agent_run_id=trace_context.get("agent_run_id") if trace_context else None,
                created_at=datetime.utcnow()
            )
        )
```

---

## 8. 为什么不直接用 LiteLLM

### 8.1 可以用 LiteLLM 作为内部实现

✅ **LiteLLM 的优势**：
- 支持多家 Provider
- 统一接口
- 内置重试

✅ **使用方式**：
```python
class LiteLLMProvider(BaseProvider):
    """基于 LiteLLM 的 Provider"""
    
    def __init__(self, model: str):
        self.model = model
    
    async def chat(self, model: str, messages: list[dict], **kwargs):
        import litellm
        
        response = await litellm.acompletion(
            model=model or self.model,
            messages=messages,
            **kwargs
        )
        
        return self.normalize_response(response)
```

### 8.2 但 ModelGateway 接口必须是我们自己的

**原因**：
- 避免被 LiteLLM API 绑死
- 可以随时替换内部实现
- 可以加入业务逻辑（权益路由、成本控制）

---

## 9. 测试要点

### 9.1 Provider 测试

```python
async def test_deepseek_provider():
    provider = DeepSeekProvider(api_key="test")
    
    response = await provider.chat(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "你好"}]
    )
    
    assert response.text is not None
    assert response.usage.total_tokens > 0
    assert response.provider == "DeepSeekProvider"
```

### 9.2 Fallback 测试

```python
async def test_fallback_on_failure():
    gateway = ModelGateway(...)
    
    # 模拟主 Provider 失败
    with patch.object(primary_provider, 'chat', side_effect=Exception()):
        response = await gateway.chat(...)
        
        # 应该降级到 fallback
        assert response.provider == fallback_provider.name
```

---

## 10. 关键要点

1. **所有模型调用必须经过 Gateway**
2. **Provider 统一适配，业务层无感知**
3. **熔断降级保证可用性**
4. **Token 和成本统一追踪**
5. **可以用 LiteLLM 但接口必须自己定义**
