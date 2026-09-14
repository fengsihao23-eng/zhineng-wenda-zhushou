import React from 'react';
import { useStreamChat } from '../hooks/useStreamChat';
import { MessageList } from './MessageList';
import { InputBox } from './InputBox';
import './ChatContainer.css';

interface ChatContainerProps {
  sessionId: string;
  sessions?: Array<{
    id: string;
    title: string | null;
    message_count: number;
  }>;
  onSelectSession?: (sessionId: string) => void;
  onNewSession?: () => void;
  onArchiveSession?: () => void;
}

export const ChatContainer: React.FC<ChatContainerProps> = ({
  sessionId,
  sessions = [],
  onSelectSession,
  onNewSession,
  onArchiveSession,
}) => {
  const { messages, isStreaming, error, canRetry, sendMessage, cancelStream, retryLast, clearError } = useStreamChat({
    sessionId
  });

  return (
    <div className="chat-container">
      <div className="chat-header">
        <div className="chat-header__toolbar">
          <select
            className="chat-header__sessions"
            value={sessionId}
            onChange={event => onSelectSession?.(event.target.value)}
            aria-label="选择会话"
          >
            {sessions.map(session => (
              <option key={session.id} value={session.id}>
                {session.title || `会话（${session.message_count} 条消息）`}
              </option>
            ))}
          </select>
          <button type="button" className="chat-header__action" onClick={onNewSession}>
            新会话
          </button>
          <button type="button" className="chat-header__action" onClick={onArchiveSession}>
            结束会话
          </button>
        </div>
        <h1 className="chat-header__title">智能问答助手</h1>
        <p className="chat-header__subtitle">问我关于你成绩的任何问题</p>
      </div>

      {error && (
        <div className="error-banner">
          <span className="error-banner__icon">⚠️</span>
          <span className="error-banner__text">{error}</span>
          {canRetry && (
            <button className="error-banner__retry" onClick={() => void retryLast()}>
              重试
            </button>
          )}
          <button className="error-banner__close" onClick={clearError}>
            ✕
          </button>
        </div>
      )}

      <MessageList messages={messages} isStreaming={isStreaming} />

      <InputBox onSend={sendMessage} onCancel={cancelStream} disabled={isStreaming} />
    </div>
  );
};
