import { describe, expect, it } from 'vitest';
import { shouldSendOnEnter } from './chatInput';

const enter = { key: 'Enter', shiftKey: false, isComposing: false, keyCode: 13, repeat: false };

describe('聊天输入法与 Enter', () => {
  it('普通 Enter 发送，Shift+Enter 和其它键不发送', () => {
    expect(shouldSendOnEnter(enter, false)).toBe(true);
    expect(shouldSendOnEnter({ ...enter, shiftKey: true }, false)).toBe(false);
    expect(shouldSendOnEnter({ ...enter, key: 'a' }, false)).toBe(false);
  });

  it('组合态、原生组合标志和 WebKit 229 都不发送', () => {
    expect(shouldSendOnEnter(enter, true)).toBe(false);
    expect(shouldSendOnEnter({ ...enter, isComposing: true }, false)).toBe(false);
    expect(shouldSendOnEnter({ ...enter, keyCode: 229 }, false)).toBe(false);
    expect(shouldSendOnEnter(enter, false)).toBe(true);
  });

  it('长按 Enter 产生的重复键事件不重复发送', () => {
    expect(shouldSendOnEnter({ ...enter, repeat: true }, false)).toBe(false);
  });
});
