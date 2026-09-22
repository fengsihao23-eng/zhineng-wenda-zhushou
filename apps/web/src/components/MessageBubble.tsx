import React, { lazy, Suspense } from 'react';
const AnswerText = lazy(() => import('./AnswerText'));
import { Message } from '../hooks/useStreamChat';
import './MessageBubble.css';
import { EvidenceButton, MessageFeedback } from '../features/education/LearningPanels';

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
          {message.role === 'assistant' ? <Suspense fallback={message.content}><AnswerText content={message.content} /></Suspense> : message.content}
        </div>
        {message.role === 'assistant' && message.sources && message.sources.length > 0 && (
          <div className="message__sources">
            <span>回答依据</span>
            {message.sources.slice(0, 4).map((source, index) => (
              <div className="message__source" key={`${String(source.id || source.resource_id || index)}`}>
                {message.agent_run_id ? <EvidenceButton messageId={message.id} index={index} label={String(source.label || source.name || source.type || '数据记录')} /> : <b>{String(source.label || source.name || source.type || '数据记录')}</b>}
                {source.as_of != null && <small>{String(source.as_of).slice(0, 10)}</small>}
              </div>
            ))}
          </div>
        )}
        {message.role === 'assistant' && message.agent_run_id && <MessageFeedback id={message.id} />}
        <div className="message__meta">
          {formatTime(message.created_at)}
        </div>
      </div>
    </div>
  );
};
