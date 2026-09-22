# PRD-11: 前端 Chat 界面设计

---
Status: draft
Type: DESIGN-REFERENCE
Owner: 前端工程
Last verified: 2026-09-11
Evidence: UI/交互设计参考；可用性以 Playwright 主流程和人工试点验收为准。
Supersedes: 旧版 Chat UI 完成声明
---

> 本文是交互参考。会话、SSE、重试和断线恢复必须以 V2 API 契约实现。

## 1. 界面总览

### 1.1 页面结构

```text
┌─────────────────────────────────────────┐
│  Header (顶部导航)                       │
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────┐  ┌────────────────────┐   │
│  │         │  │                    │   │
│  │ Session │  │   Chat Messages    │   │
│  │  List   │  │                    │   │
│  │         │  │   (消息列表)        │   │
│  │         │  │                    │   │
│  └─────────┘  ├────────────────────┤   │
│               │   Input Box        │   │
│               │   (输入框)          │   │
│               └────────────────────┘   │
│                                         │
└─────────────────────────────────────────┘
```

---

## 2. 核心组件

### 2.1 ChatContainer

```typescript
interface ChatContainerProps {
  sessionId: string;
}

const ChatContainer: React.FC<ChatContainerProps> = ({ sessionId }) => {
  const { messages, isStreaming, sendMessage } = useStreamChat(sessionId);
  
  return (
    <div className="chat-container">
      <MessageList messages={messages} />
      <InputBox 
        onSend={sendMessage} 
        disabled={isStreaming}
      />
    </div>
  );
};
```

### 2.2 MessageList

```typescript
interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  agent_run_id?: string;
}

const MessageList: React.FC<{ messages: Message[] }> = ({ messages }) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);
  
  return (
    <div className="message-list">
      {messages.map(msg => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      <div ref={messagesEndRef} />
    </div>
  );
};
```

### 2.3 MessageBubble

```typescript
const MessageBubble: React.FC<{ message: Message }> = ({ message }) => {
  return (
    <div className={`message message--${message.role}`}>
      <div className="message__avatar">
        {message.role === 'user' ? <UserIcon /> : <BotIcon />}
      </div>
      <div className="message__content">
        <div className="message__text">
          {message.content}
        </div>
        <div className="message__meta">
          {formatTime(message.created_at)}
        </div>
      </div>
    </div>
  );
};
```

### 2.4 InputBox

```typescript
const InputBox: React.FC<{
  onSend: (content: string) => void;
  disabled: boolean;
}> = ({ onSend, disabled }) => {
  const [value, setValue] = useState('');
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim() || disabled) return;
    
    onSend(value);
    setValue('');
  };
  
  return (
    <form className="input-box" onSubmit={handleSubmit}>
      <textarea
        className="input-box__textarea"
        value={value}
        onChange={e => setValue(e.target.value)}
        placeholder="问我任何关于成绩的问题..."
        disabled={disabled}
        rows={3}
      />
      <button 
        className="input-box__send"
        type="submit"
        disabled={disabled || !value.trim()}
      >
        {disabled ? '生成中...' : '发送'}
      </button>
    </form>
  );
};
```

---

## 3. 状态管理

### 3.1 useStreamChat Hook

```typescript
function useStreamChat(sessionId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // 加载历史消息
  useEffect(() => {
    loadMessages();
  }, [sessionId]);
  
  const loadMessages = async () => {
    try {
      const response = await fetch(
        `/api/v1/chat/sessions/${sessionId}/messages`,
        {
          headers: {
            'Authorization': `Bearer ${getToken()}`
          }
        }
      );
      const data = await response.json();
      setMessages(data.items);
    } catch (err) {
      setError('加载消息失败');
    }
  };
  
  const sendMessage = async (content: string) => {
    // 添加用户消息
    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content,
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMessage]);
    
    // 开始流式接收
    setIsStreaming(true);
    setError(null);
    
    try {
      const eventSource = new EventSource(
        `/api/v1/chat/sessions/${sessionId}/stream?content=${encodeURIComponent(content)}`,
        {
          headers: {
            'Authorization': `Bearer ${getToken()}`
          }
        }
      );
      
      let assistantMessageId: string | null = null;
      
      eventSource.addEventListener('message_start', (e) => {
        const data = JSON.parse(e.data);
        assistantMessageId = data.message_id;
        
        setMessages(prev => [
          ...prev,
          {
            id: assistantMessageId!,
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString()
          }
        ]);
      });
      
      eventSource.addEventListener('content_delta', (e) => {
        const data = JSON.parse(e.data);
        
        setMessages(prev => prev.map(msg =>
          msg.id === assistantMessageId
            ? { ...msg, content: msg.content + data.delta }
            : msg
        ));
      });
      
      eventSource.addEventListener('message_end', () => {
        setIsStreaming(false);
        eventSource.close();
      });
      
      eventSource.addEventListener('error', (e) => {
        setIsStreaming(false);
        setError('连接中断，请重试');
        eventSource.close();
      });
      
    } catch (err) {
      setIsStreaming(false);
      setError('发送失败，请重试');
    }
  };
  
  return {
    messages,
    isStreaming,
    error,
    sendMessage,
    loadMessages
  };
}
```

---

## 4. 样式设计

### 4.1 CSS 基础

```css
/* Chat Container */
.chat-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-width: 1200px;
  margin: 0 auto;
  background: #f5f5f5;
}

/* Message List */
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

/* Message Bubble */
.message {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.message--user {
  flex-direction: row-reverse;
}

.message__avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #e0e0e0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.message__content {
  max-width: 70%;
}

.message--user .message__content {
  background: #1976d2;
  color: white;
}

.message--assistant .message__content {
  background: white;
  color: #333;
}

.message__text {
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.5;
}

.message__meta {
  font-size: 12px;
  color: #999;
  padding: 4px 16px;
}

/* Input Box */
.input-box {
  display: flex;
  gap: 12px;
  padding: 20px;
  background: white;
  border-top: 1px solid #e0e0e0;
}

.input-box__textarea {
  flex: 1;
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  resize: none;
  font-size: 14px;
}

.input-box__send {
  padding: 12px 24px;
  background: #1976d2;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}

.input-box__send:disabled {
  background: #ccc;
  cursor: not-allowed;
}
```

---

## 5. 交互细节

### 5.1 加载状态

```typescript
const LoadingIndicator = () => (
  <div className="message message--assistant">
    <div className="message__avatar">
      <BotIcon />
    </div>
    <div className="message__content">
      <div className="typing-indicator">
        <span></span>
        <span></span>
        <span></span>
      </div>
    </div>
  </div>
);

// CSS
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 12px 16px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #999;
  animation: typing 1.4s infinite;
}

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-10px); }
}
```

### 5.2 错误提示

```typescript
const ErrorBanner: React.FC<{ error: string; onRetry: () => void }> = ({ error, onRetry }) => (
  <div className="error-banner">
    <span>{error}</span>
    <button onClick={onRetry}>重试</button>
  </div>
);
```

### 5.3 快捷问题

```typescript
const QuickQuestions: React.FC<{ onSelect: (q: string) => void }> = ({ onSelect }) => {
  const questions = [
    "我这次考得怎样？",
    "比上次进步了吗？",
    "哪科最高？",
    "哪几题丢分多？"
  ];
  
  return (
    <div className="quick-questions">
      {questions.map(q => (
        <button
          key={q}
          className="quick-question"
          onClick={() => onSelect(q)}
        >
          {q}
        </button>
      ))}
    </div>
  );
};
```

---

## 6. 响应式设计

### 6.1 移动端适配

```css
@media (max-width: 768px) {
  .chat-container {
    height: 100dvh; /* 动态视口高度 */
  }
  
  .message__content {
    max-width: 85%;
  }
  
  .input-box {
    padding: 12px;
  }
  
  .input-box__textarea {
    font-size: 16px; /* 防止 iOS 缩放 */
  }
}
```

---

## 7. 一期不做的功能

### 7.1 暂不实现

- ❌ Markdown 渲染（复杂格式）
- ❌ 代码高亮
- ❌ 图片/文件上传
- ❌ 语音输入
- ❌ 消息编辑/删除
- ❌ 消息搜索
- ❌ 多轮对话分支

### 7.2 后续考虑

- ⏳ Markdown 基础支持（加粗、列表）
- ⏳ 消息点赞/点踩
- ⏳ 消息分享
- ⏳ 对话导出

---

## 8. 性能优化

### 8.1 虚拟滚动

当消息数量 > 100 时使用虚拟滚动：

```typescript
import { useVirtualizer } from '@tanstack/react-virtual';

const VirtualMessageList = ({ messages }) => {
  const parentRef = useRef<HTMLDivElement>(null);
  
  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 100, // 估计每条消息高度
  });
  
  return (
    <div ref={parentRef} className="message-list">
      <div style={{ height: `${virtualizer.getTotalSize()}px` }}>
        {virtualizer.getVirtualItems().map(item => (
          <div
            key={item.key}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${item.start}px)`
            }}
          >
            <MessageBubble message={messages[item.index]} />
          </div>
        ))}
      </div>
    </div>
  );
};
```

### 8.2 防抖输入

```typescript
const DebouncedTextarea = ({ onChange, ...props }) => {
  const debouncedChange = useMemo(
    () => debounce(onChange, 300),
    [onChange]
  );
  
  return <textarea onChange={debouncedChange} {...props} />;
};
```

---

## 9. 测试

### 9.1 组件测试

```typescript
import { render, screen, fireEvent } from '@testing-library/react';

test('sends message on button click', async () => {
  const onSend = jest.fn();
  
  render(<InputBox onSend={onSend} disabled={false} />);
  
  const textarea = screen.getByPlaceholderText(/问我任何/);
  const button = screen.getByText('发送');
  
  fireEvent.change(textarea, { target: { value: '测试消息' } });
  fireEvent.click(button);
  
  expect(onSend).toHaveBeenCalledWith('测试消息');
});
```

### 9.2 E2E 测试

```typescript
test('complete chat flow', async ({ page }) => {
  await page.goto('/chat');
  
  // 等待加载
  await page.waitForSelector('.chat-container');
  
  // 输入消息
  await page.fill('.input-box__textarea', '我这次考得怎样？');
  await page.click('.input-box__send');
  
  // 等待回复
  await page.waitForSelector('.message--assistant');
  
  // 验证回复内容
  const reply = await page.textContent('.message--assistant');
  expect(reply).toContain('总分');
});
```

---

## 10. 关键要点

1. **一期保持简单，纯文本对话**
2. **使用 SSE 实现流式体验**
3. **做好加载、错误、空状态**
4. **移动端优先设计**
5. **性能优化留待消息量大时**
6. **不过早引入复杂 UI 库**
