import { useEffect, useId, useRef, type ReactNode } from 'react'
import './HelpTip.css'

/** Click to open; Escape, the close button, or an outside click dismisses it. */
export function HelpTip({ children, label = '说明' }: { children: ReactNode; label?: string }) {
  const ref = useRef<HTMLDetailsElement>(null)
  const id = useId()
  const close = () => ref.current?.removeAttribute('open')
  useEffect(() => {
    const pointer = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) ref.current?.removeAttribute('open')
    }
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && ref.current?.open) {
        event.preventDefault()
        event.stopPropagation()
        ref.current.removeAttribute('open')
        ref.current.querySelector('summary')?.focus()
      }
    }
    document.addEventListener('pointerdown', pointer)
    document.addEventListener('keydown', keyboard)
    return () => {
      document.removeEventListener('pointerdown', pointer)
      document.removeEventListener('keydown', keyboard)
    }
  }, [])
  return <details ref={ref} className="help-tip" onToggle={() => {
    const content = ref.current?.querySelector<HTMLElement>('.help-tip__content')
    if (!ref.current?.open || !content || getComputedStyle(content).position === 'fixed') return
    content.style.left = '0px'
    content.style.right = 'auto'
    const bounds = content.getBoundingClientRect()
    const shift = Math.min(0, window.innerWidth - 16 - bounds.right)
    content.style.left = `${Math.max(16 - bounds.left, shift)}px`
  }}>
    <summary aria-controls={id}><span aria-hidden="true">ⓘ</span> {label}</summary>
    <div id={id} className="help-tip__content" role="note" aria-label={label}>
      <div className="help-tip__heading"><strong>{label}</strong><button type="button" aria-label={`关闭${label}`} onClick={() => { close(); ref.current?.querySelector('summary')?.focus() }}>×</button></div>
      <div>{children}</div>
    </div>
  </details>
}
