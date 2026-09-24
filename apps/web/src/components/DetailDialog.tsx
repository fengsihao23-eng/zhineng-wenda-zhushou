import { useId, useLayoutEffect, useRef, type ReactNode } from 'react'
import './DetailDialog.css'

export function DetailDialog({ title, onClose, children, busy = false }: { title: string; onClose: () => void; children: ReactNode; busy?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  useLayoutEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])
  return <dialog className="detail-dialog" ref={ref} aria-labelledby={titleId} onClose={onClose} onCancel={event => { if (busy) event.preventDefault() }}>
    <div className="detail-dialog__heading"><h2 id={titleId}>{title}</h2><button type="button" className="secondary-button" disabled={busy} onClick={() => ref.current?.close()}>关闭</button></div>
    {children}
  </dialog>
}
