type ChatKeyEvent = Pick<KeyboardEvent, 'key' | 'shiftKey' | 'isComposing' | 'keyCode' | 'repeat'>;

/** A composition-confirming Enter belongs to the input method, not chat. */
export function shouldSendOnEnter(event: ChatKeyEvent, composing: boolean): boolean {
  return event.key === 'Enter'
    && !event.shiftKey
    && !event.repeat
    && !composing
    && !event.isComposing
    && event.keyCode !== 229;
}
