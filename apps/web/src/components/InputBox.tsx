import React, { useRef, useState, KeyboardEvent } from 'react';
import { shouldSendOnEnter } from '../utils/chatInput';
import './InputBox.css';

interface InputBoxProps {
  onSend: (content: string) => void;
  onCancel?: () => void;
  disabled: boolean;
}

export const InputBox: React.FC<InputBoxProps> = ({ onSend, onCancel, disabled }) => {
  const [value, setValue] = useState('');
  const composingRef = useRef(false);
  const valueRef = useRef('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const content = valueRef.current;
    if (!content.trim() || disabled || composingRef.current) return;

    // Update the synchronous guard before React re-renders; two submit events
    // in one frame must not send the same draft twice.
    valueRef.current = '';
    setValue('');
    onSend(content);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Includes the WebKit keyCode=229 fallback used while IME text commits.
    if (shouldSendOnEnter(e.nativeEvent, composingRef.current)) {
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
          onChange={e => { valueRef.current = e.target.value; setValue(e.target.value); }}
          onCompositionStart={() => { composingRef.current = true; }}
          onCompositionEnd={() => { composingRef.current = false; }}
          onBlur={() => { composingRef.current = false; }}
          onKeyDown={handleKeyDown}
          placeholder="问我任何关于成绩的问题... (Enter发送，Shift+Enter换行)"
          disabled={disabled}
          aria-label="提问内容"
          rows={1}
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
