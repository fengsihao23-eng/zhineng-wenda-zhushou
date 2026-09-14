# PRD-13: SSE 流式传输设计

---
Status: active
Owner: API 与前端工程
Last verified: 2026-09-11
Evidence: V2 SSE 事件规范；必须由 SSE 契约测试、断线恢复测试和 Nginx 验证支持。
Supersedes: 旧版 SSE 格式和客户端实现
---

> 本文只定义 V2 SSE 事件。前端通过 `fetch` POST 读取流；任何旧 EventSource 示例均为历史参考。

## 1. 概述

使用 Server-Sent Events (SSE) 实现流式对话，提升用户体验。

### 1.1 为什么选择 SSE

**SSE vs WebSocket**：

| 特性 | SSE | WebSocket |
|---|---|---|
| 单向/双向 | 单向（服务器→客户端） | 双向 |
| 协议 | HTTP | WebSocket 协议 |
| 重连 | 自动重连 | 需手动实现 |
| 兼容性 | 更好 | 需特殊支持 |
| 适用场景 | 流式推送 | 实时双向 |

**Chat 场景分析**：
- ✅ 只需服务器推送（单向）
- ✅ 用户提问用普通 HTTP POST
- ✅ 模型生成用 SSE 推送
- ❌ 不需要双向实时通信

**结论**：SSE 足够，更简单。

---

## 2. SSE 协议

### 2.1 SSE 消息格式

```text
event: message_start
data: {"request_id":"uuid","seq":1,"data":{"message_id":"uuid"}}

event: content_delta
data: {"request_id":"uuid","seq":2,"data":{"content":"你这次"}}

event: content_delta
data: {"request_id":"uuid","seq":3,"data":{"content":"考试"}}

event: message_end
data: {"request_id":"uuid","seq":4,"data":{"message_id":"uuid","finish_reason":"stop"}}
```

`data` 外层契约固定为 `{request_id, seq, data}`。事件名称、路径、请求体、错误码和恢复方式以 [PRD-12 API 接口规范](12_API接口规范.md) 为唯一来源。

### 2.2 事件类型

| Event | 说明 | Data |
|---|---|---|
| message_start | 消息开始 | `{"message_id": "uuid"}` |
| content_delta | 内容增量 | `{"content": "文本片段"}` |
| source | 数据来源 | `{"source_type": "score", "batch_id": "uuid"}` |
| message_end | 消息结束 | `{"message_id": "uuid", "agent_run_id": "uuid"}` |
| error | 错误 | `{"code": "...", "message": "..."}` |
| done | 流结束 | `{"message_id": "uuid"}` |

---

## 3. FastAPI SSE 实现

### 3.1 SSE 端点

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

@router.post("/chat/sessions/{session_id}/stream")
async def stream_chat(
    session_id: str,
    request: ChatMessageRequest,
    current_user: User = Depends(get_current_user)
):
    """流式 Chat 接口"""
    
    async def event_generator():
        """SSE 事件生成器"""
        seq = 0
        request_id = str(uuid4())

        def frame(event: str, payload: dict):
            nonlocal seq
            seq += 1
            return {"event": event, "data": json.dumps({"request_id": request_id, "seq": seq, "data": payload})}

        try:
            # 1. 创建消息
            message_id = str(uuid4())
            
            yield frame("message_start", {"message_id": message_id})
            
            # 2. 运行 Agent（流式）
            async for chunk in agent_loop.run_stream(
                actor=current_user,
                query=request.content,
                session_id=session_id
            ):
                if chunk.type == "content":
                    yield frame("content_delta", {"content": chunk.content})
            
            # 3. 消息结束
            yield frame("message_end", {"message_id": message_id, "agent_run_id": chunk.agent_run_id})
            yield frame("done", {"message_id": message_id})
        
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield {
                "event": "error",
                "data": json.dumps({
                    "request_id": request_id,
                    "seq": seq + 1,
                    "data": {
                    "code": "STREAM_ERROR",
                    "message": "流式响应失败，请重试"
                    }
                })
            }
    
    return EventSourceResponse(event_generator())
```

### 3.2 Agent Loop 流式支持

```python
class AgentLoop:
    async def run_stream(
        self,
        actor: AuthenticatedStudent,
        query: str,
        session_id: str
    ) -> AsyncIterator[StreamChunk]:
        """流式运行 Agent"""
        
        # 构建上下文
        context = await self.context_builder.build(...)
        
        # 准备消息
        messages = self._build_messages(context, query)
        
        # 流式调用模型
        async for chunk in self.model_gateway.stream(
            model="deepseek-chat",
            messages=messages,
            tools=available_tools
        ):
            if chunk.type == "content":
                yield StreamChunk(
                    type="content",
                    content=chunk.delta
                )
            
            elif chunk.type == "tool_call":
                # 执行 Tool
                tool_result = await self._execute_tool(chunk.tool_call)
                
                yield StreamChunk(
                    type="tool_call",
                    tool_name=chunk.tool_call.name,
                    status="completed"
                )
        
        # 最终返回 run_id
        yield StreamChunk(
            type="done",
            agent_run_id=state.run_id
        )
```

---

## 4. 前端 SSE 客户端（V2 规范）

SSE 必须使用 `fetch` 对正式接口发起 `POST`，因为请求需要 JSON body 和 `Authorization` 头。不得使用原生 `EventSource`，也不得把消息内容拼到 URL 查询参数中。

```typescript
async function streamMessage(sessionId: string, content: string, token: string) {
  const response = await fetch(`/api/v1/chat/sessions/${sessionId}/stream`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ content }),
  });
  if (!response.ok || !response.body) throw new Error('SSE_REQUEST_FAILED');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let lastSeq = 0;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      const eventName = frame.match(/^event: (.+)$/m)?.[1];
      const rawData = frame.match(/^data: (.+)$/m)?.[1];
      if (!eventName || !rawData) continue;
      const event = JSON.parse(rawData) as { request_id: string; seq: number; data: unknown };
      if (event.seq <= lastSeq) continue;
      lastSeq = event.seq;
      handleStreamEvent(eventName, event.data);
    }
  }
}
```

当前 V2 试点客户端必须处理 `message_start`、`content_delta`、`source`、`tool_call_start`、`tool_call_end`、`message_end`、`error` 和 `done`，按 `seq` 去重，并保存最后序号用于断线恢复。工具事件只用于可观测性，客户端不应依赖其返回顺序来渲染答案。

---

## 5. Nginx 配置

### 5.1 SSE 专用配置

```nginx
location /api/v1/chat/sessions {
    proxy_pass http://api:8000;
    
    # SSE 关键配置
    proxy_buffering off;           # 关闭缓冲
    proxy_cache off;               # 关闭缓存
    proxy_read_timeout 300s;       # 5分钟超时
    proxy_connect_timeout 10s;
    
    # HTTP/1.1 支持
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    
    # 转发头
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## 6. 降级策略

### 6.1 非流式降级

如果浏览器不支持 SSE 或网络不稳定，降级为普通 HTTP：

```javascript
function useFallbackChat() {
  // 使用普通 POST 接口
  const response = await fetch(`/api/v1/chat/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ content: message })
  });
  
  const data = await response.json();
  return data;
}
```

---

## 7. 性能优化

### 7.1 连接复用

每条用户消息建立一次带请求体的 POST 流，收到 `done` 或 `error` 后关闭 reader。不要创建未定义的会话级 `/events` 路由，也不要把 SSE 与普通消息 POST 拆成两条无法关联的连接。

### 7.2 心跳保活

如反向代理需要心跳，使用 SSE 注释帧 `: ping\\n\\n`，不得新增未在本规范登记的事件名称；心跳不得被客户端当作业务事件或计入 `seq`。

---

## 8. 错误处理

### 8.1 超时处理

```python
@router.post("/chat/sessions/{session_id}/stream")
async def stream_chat(...):
    async def event_generator():
        try:
            # 设置超时
            async with asyncio.timeout(60):
                async for chunk in agent_loop.run_stream(...):
                    yield chunk
        
        except asyncio.TimeoutError:
            yield frame("error", {"code": "TIMEOUT", "message": "响应超时，请重试"})
    
    return EventSourceResponse(event_generator())
```

### 8.2 客户端重连

客户端在请求失败或连接中断后，使用最后收到的 `seq` 重新发起同一 POST 请求，并在服务端支持时携带 `Last-Event-ID` 或请求体中的 `last_seq`。重连最多 3 次，指数退避；收到 `error` 后不得静默重试。

---

## 9. 测试

### 9.1 手动测试

```bash
# 使用 curl 测试 SSE
curl -N -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream" -H "Content-Type: application/json" \
  -d '{"content":"测试"}' \
  "http://localhost:8000/api/v1/chat/sessions/{session_id}/stream"
```

### 9.2 自动化测试

```python
async def test_sse_stream():
    """测试 SSE 流式响应"""
    
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            f"/api/v1/chat/sessions/{session_id}/stream",
            json={"content": "测试"},
            headers={"Authorization": f"Bearer {token}"}
        ) as response:
            events = []
            
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = json.loads(line.split(":", 1)[1])
                    events.append({"type": event_type, "data": data})
            
            # 验证事件顺序和 seq 单调递增
            assert events[0]["type"] == "message_start"
            assert events[-1]["type"] == "done"
```

---

## 10. 关键要点

1. **SSE 适合单向推送，Chat 场景足够**
2. **Nginx 必须配置 `proxy_buffering off`**
3. **客户端用 fetch POST 读取流，不能使用 EventSource**
4. **支持降级到普通 HTTP**
5. **设置合理的超时和心跳**
6. **前端做好重连和错误处理**
