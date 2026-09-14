import { useCallback, useEffect, useRef, useState } from 'react';
import { apiError, apiFetch } from '../services/api';

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  agent_run_id?: string;
  sources?: Array<Record<string, unknown>>;
}

interface UseStreamChatOptions {
  sessionId: string;
}

interface UseStreamChatReturn {
  messages: Message[];
  isStreaming: boolean;
  error: string | null;
  canRetry: boolean;
  sendMessage: (content: string, clientMessageId?: string) => Promise<void>;
  cancelStream: () => void;
  retryLast: () => Promise<void>;
  loadMessages: () => Promise<void>;
  clearError: () => void;
}

type ServerEvent = {
  request_id: string;
  seq: number;
  data: Record<string, any>;
};

export function useStreamChat({ sessionId }: UseStreamChatOptions): UseStreamChatReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const lastFailedRequestRef = useRef<{ content: string; clientMessageId: string } | null>(null);
  const resumeFromSeqRef = useRef<number | null>(null);
  const cursorKey = `stream_cursor:${sessionId}`;

  const loadMessages = useCallback(async () => {
    const response = await apiFetch(`/chat/sessions/${sessionId}/messages`);
    if (!response.ok) throw await apiError(response, '加载消息失败');
    const data = await response.json();
    setMessages(Array.isArray(data) ? data : data.messages || []);
  }, [sessionId]);

  useEffect(() => {
    loadMessages().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : '加载消息失败');
    });
    return () => abortRef.current?.abort();
  }, [loadMessages]);

  const sendMessage = useCallback(async (content: string, requestedClientMessageId?: string) => {
    if (!content.trim() || isStreaming) return;
    const normalizedContent = content.trim();
    const clientMessageId = requestedClientMessageId || generateId();
    setError(null);
    setCanRetry(false);
    setIsStreaming(true);
    const userMessage: Message = {
      id: clientMessageId,
      role: 'user',
      content: normalizedContent,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMessage]);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const streamHeaders = new Headers({ Accept: 'text/event-stream' });
      if (resumeFromSeqRef.current !== null) {
        streamHeaders.set('Last-Event-ID', String(resumeFromSeqRef.current));
        resumeFromSeqRef.current = null;
      }
      const response = await apiFetch(`/chat/sessions/${sessionId}/stream`, {
        method: 'POST',
        signal: controller.signal,
        body: JSON.stringify({ content: normalizedContent, client_message_id: userMessage.id }),
        headers: streamHeaders,
      });
      if (!response.ok) throw await apiError(response, '发送消息失败');
      if (!response.body) throw new Error('服务器没有返回消息流');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const assistantId = generateId();
      let lastSeq = 0;
      let assistantCreated = false;
      let streamCompleted = false;
      let streamErrored = false;
      let requestId: string | null = null;

      const ensureAssistant = () => {
        if (assistantCreated) return;
        assistantCreated = true;
        setMessages(prev => [...prev, {
          id: assistantId,
          role: 'assistant',
          content: '',
          created_at: new Date().toISOString(),
          sources: [],
        }]);
      };

      const processBlock = (block: string) => {
        const lines = block.split(/\r?\n/).map(line => line.trimEnd());
        const eventLine = lines.find(line => line.startsWith('event:'));
        const dataLines = lines.filter(line => line.startsWith('data:'));
        const dataLine = dataLines.length > 0 ? dataLines.map(line => line.slice(5).trimStart()).join('\n') : null;
        if (!eventLine || !dataLine) return;
        const eventName = eventLine.slice(6).trim();
        let event: ServerEvent;
        try {
          event = JSON.parse(dataLine) as ServerEvent;
        } catch {
          streamErrored = true;
          setError('服务器返回了无效的消息格式，请重试');
          return;
        }
        requestId = event.request_id || requestId;
        if (event.seq <= lastSeq) return;
        lastSeq = event.seq;
        try {
          sessionStorage.setItem(cursorKey, JSON.stringify({ request_id: requestId, seq: lastSeq }));
        } catch {
          // Storage can be unavailable in privacy mode; the stream still works.
        }

        if (eventName === 'message_start' || eventName === 'content_delta' || eventName === 'source' || eventName === 'message_end') {
          ensureAssistant();
        }
        if (eventName === 'content_delta') {
          setMessages(prev => prev.map(message => message.id === assistantId
            ? { ...message, content: message.content + (event.data.content || '') }
            : message));
        } else if (eventName === 'source') {
          setMessages(prev => prev.map(message => message.id === assistantId
            ? { ...message, sources: [...(message.sources || []), event.data] }
            : message));
        } else if (eventName === 'message_end') {
          setMessages(prev => prev.map(message => message.id === assistantId
            ? { ...message, id: event.data.message_id || assistantId, agent_run_id: event.data.agent_run_id }
            : message));
        } else if (eventName === 'done') {
          streamCompleted = true;
          lastFailedRequestRef.current = null;
          setCanRetry(false);
          try {
            sessionStorage.removeItem(cursorKey);
          } catch {
            // Ignore storage errors.
          }
        } else if (eventName === 'error') {
          streamErrored = true;
          setError(event.data.message || '生成回答时出错');
        }
      };

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() || '';
        blocks.filter(Boolean).forEach(processBlock);
      }
      if (buffer.trim()) processBlock(buffer);
      if (!streamCompleted && !streamErrored) {
        throw new Error('连接中断，请重试');
      }
      if (streamErrored) {
        lastFailedRequestRef.current = { content: normalizedContent, clientMessageId };
        setCanRetry(true);
        // The server may have committed the assistant message just before the
        // connection dropped. Refresh history before showing the retry action.
        await loadMessages().catch(() => undefined);
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        lastFailedRequestRef.current = { content: normalizedContent, clientMessageId };
        setCanRetry(true);
        setError('已停止生成，可点击重试');
      } else {
        lastFailedRequestRef.current = { content: normalizedContent, clientMessageId };
        setCanRetry(true);
        setError(err instanceof Error ? err.message : '发送失败，请重试');
        await loadMessages().catch(() => undefined);
      }
    } finally {
      abortRef.current = null;
      setIsStreaming(false);
    }
  }, [isStreaming, sessionId]);

  const cancelStream = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const retryLast = useCallback(async () => {
    const failedRequest = lastFailedRequestRef.current;
    if (!failedRequest) return;
    try {
      const cursor = JSON.parse(sessionStorage.getItem(cursorKey) || 'null') as { seq?: number } | null;
      if (cursor?.seq) resumeFromSeqRef.current = cursor.seq;
    } catch {
      // Ignore malformed or unavailable cursors.
    }
    lastFailedRequestRef.current = null;
    await sendMessage(failedRequest.content, failedRequest.clientMessageId);
  }, [cursorKey, sendMessage]);

  return {
    messages,
    isStreaming,
    error,
    canRetry,
    sendMessage,
    cancelStream,
    retryLast,
    loadMessages,
    clearError: () => setError(null),
  };
}

function generateId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return `00000000-0000-4000-8000-${Date.now().toString(16).padStart(12, '0')}`;
}
