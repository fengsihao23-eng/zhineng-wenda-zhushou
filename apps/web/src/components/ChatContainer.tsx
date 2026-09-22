import React from 'react';
import { useStreamChat } from '../hooks/useStreamChat';
import { MessageList } from './MessageList';
import { InputBox } from './InputBox';
import { ErrorDisplay } from './ErrorDisplay';
import './ChatContainer.css';
import { useApiMutation, useJsonQuery } from '../hooks/useApi';

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
  const { messages, isStreaming, isLoading, error, canRetry, sendMessage, cancelStream, retryLast, loadMessages, clearError } = useStreamChat({
    sessionId
  });

  const context = useJsonQuery<{ exam_id: string | null; subject_id: string | null; version: number; exams: Array<{id:string;name:string}>; subjects: Array<{id:string;name:string}> }>(`/chat/sessions/${sessionId}/context`);
  const changeContext = useApiMutation<unknown, {exam_id:string|null;subject_id:string|null;expected_version:number}>(`/chat/sessions/${sessionId}/context`, 'PUT', { onSuccess: () => { void context.refetch() } });

  return (
    <div className={`chat-container${messages.length === 0 ? ' is-empty' : ''}`}>
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
        <div className="wb-toolbar">
          <label>考试范围<select aria-label="问答考试范围" value={context.data?.exam_id || ''} disabled={isStreaming || changeContext.isPending || context.isLoading} onChange={event => context.data && changeContext.mutate({exam_id:event.target.value||null,subject_id:null,expected_version:context.data.version})}><option value="">最近考试</option>{context.data?.exams.map(exam=><option key={exam.id} value={exam.id}>{exam.name}</option>)}</select></label>
          <label>学科范围<select aria-label="问答学科范围" value={context.data?.subject_id || ''} disabled={isStreaming || changeContext.isPending || context.isLoading} onChange={event => context.data && changeContext.mutate({exam_id:context.data.exam_id,subject_id:event.target.value||null,expected_version:context.data.version})}><option value="">根据问题确定学科</option>{context.data?.subjects.map(subject=><option key={subject.id} value={subject.id}>{subject.name}</option>)}</select></label>
          <small>查询完成并校验后展示回答</small>
        </div>
        <ErrorDisplay error={context.error || changeContext.error} onRetry={() => { void context.refetch(); changeContext.reset() }} variant="banner" />
        <h1 className="chat-header__title">智能问答助手</h1>
        <p className="chat-header__subtitle">问我关于你成绩的任何问题</p>
      </div>

      {error && (
        <ErrorDisplay error={error} title="会话提示" variant="banner"
          onRetry={() => { void (canRetry ? retryLast() : loadMessages()).catch(() => undefined); }}
          onDismiss={clearError} />
      )}

      {isLoading ? <div className="loading-state">正在加载消息…</div> : <MessageList messages={messages} isStreaming={isStreaming} />}

      <InputBox onSend={sendMessage} onCancel={isStreaming ? cancelStream : undefined} disabled={isStreaming || isLoading || context.isLoading || changeContext.isPending || !!context.error} />
    </div>
  );
};
