import React, { useState, KeyboardEvent } from 'react';
import './InputBox.css';

interface InputBoxProps {
  onSend: (content: string) => void;
  onCancel?: () => void;
  disabled: boolean;
}

export const InputBox: React.FC<InputBoxProps> = ({ onSend, onCancel, disabled }) => {
  const [value, setValue] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim() || disabled) return;

    onSend(value);
    setValue('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Ctrl/Cmd + Enter 发送
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <form className="input-box" onSubmit={handleSubmit}>
      <div className="input-box__container">
        <textarea
          className="input-box__textarea"
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="问我任何关于成绩的问题... (Ctrl+Enter发送)"
          disabled={disabled}
          rows={3}
        />
        <button
          className="input-box__send"
          type="submit"
          disabled={disabled || !value.trim()}
        >
          {disabled ? (
            <>
              <span className="spinner"></span>
              生成中...
            </>
          ) : (
            <>
              <span className="send-icon">➤</span>
              发送
            </>
          )}
        </button>
        {disabled && onCancel && (
          <button className="input-box__cancel" type="button" onClick={onCancel}>
            停止
          </button>
        )}
      </div>
    </form>
  );
};
