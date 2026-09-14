import React, { useRef, useEffect } from 'react';
import { Message } from '../hooks/useStreamChat';
import { MessageBubble } from './MessageBubble';
import './MessageList.css';

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
}

export const MessageList: React.FC<MessageListProps> = ({ messages, isStreaming }) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  return (
    <div className="message-list">
      {messages.length === 0 && (
        <div className="message-list__empty">
          <div className="empty-state">
            <div className="empty-state__icon">💬</div>
            <h3 className="empty-state__title">开始对话</h3>
            <p className="empty-state__text">
              问我任何关于你成绩的问题
            </p>
          </div>
        </div>
      )}

      {messages.map(msg => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      {isStreaming && (
        <div className="message message--assistant">
          <div className="message__avatar">
            <div className="avatar avatar--bot">AI</div>
          </div>
          <div className="message__content">
            <div className="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
};
