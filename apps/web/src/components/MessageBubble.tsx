import React from 'react';
import { Message } from '../hooks/useStreamChat';
import './MessageBubble.css';

interface MessageBubbleProps {
  message: Message;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className={`message message--${message.role}`}>
      <div className="message__avatar">
        {message.role === 'user' ? (
          <div className="avatar avatar--user">我</div>
        ) : (
          <div className="avatar avatar--bot">AI</div>
        )}
      </div>
      <div className="message__content">
        <div className="message__text">
          {message.content}
        </div>
        {message.role === 'assistant' && message.sources && message.sources.length > 0 && (
          <div className="message__sources">
            <span>回答依据</span>
            {message.sources.slice(0, 4).map((source, index) => (
              <div className="message__source" key={`${String(source.id || source.resource_id || index)}`}>
                <b>{String(source.label || source.name || source.type || '数据记录')}</b>
                {source.as_of != null && <small>{String(source.as_of).slice(0, 10)}</small>}
              </div>
            ))}
          </div>
        )}
        <div className="message__meta">
          {formatTime(message.created_at)}
        </div>
      </div>
    </div>
  );
};
