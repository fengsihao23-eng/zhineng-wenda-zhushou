import { useId, useLayoutEffect, useRef, useState } from "react";
import { Table, type Row } from "./shared";

type Props = {
  rows: Row[];
  notes: Record<string, string>;
  checked: Record<string, boolean>;
  busy: boolean;
  onNotesChange: (notes: Record<string, string>) => void;
  onCheckedChange: (checked: Record<string, boolean>) => void;
};

export function StudentAnomalyApprovals({ rows, notes, checked, busy, onNotesChange, onCheckedChange }: Props) {
  const [commonNote, setCommonNote] = useState("");
  const selectAll = useRef<HTMLInputElement>(null);
  const hintId = useId(), statusId = useId();
  const selected = rows.filter(row => checked[row.student_id]).length;
  const missing = rows.filter(row => !notes[row.student_id]?.trim());
  const unchecked = rows.length - selected;
  useLayoutEffect(() => {
    if (selectAll.current) selectAll.current.indeterminate = selected > 0 && selected < rows.length;
  }, [selected, rows.length]);

  const fillMissing = () => {
    if (busy || !commonNote.trim()) return;
    const nextNotes = { ...notes }, nextChecked = { ...checked };
    for (const row of missing) {
      nextNotes[row.student_id] = commonNote.trim();
      nextChecked[row.student_id] = false;
    }
    onNotesChange(nextNotes);
    onCheckedChange(nextChecked);
  };

  return <div className="student-anomaly-review">
    <p id={hintId}>每人须填写核实依据并勾选审批，才能进入预览。共同依据可批量填写；依据不同的学生请单独填写。填写或修改依据后须重新勾选对应审批。</p>
    <div className="student-anomaly-batch">
      <label className="student-input-label">批量核实依据（仅填写空白项）
        <input aria-label="批量年级异常依据" value={commonNote} maxLength={500} disabled={busy}
          placeholder="填写本批相同情况的实际核实依据" onChange={e => setCommonNote(e.target.value)} />
      </label>
      <button type="button" disabled={busy || !commonNote.trim() || !missing.length} onClick={fillMissing}>填入全部空白依据（{missing.length}人）</button>
    </div>
    <div className="student-anomaly-selection">
      <label className="teacher-confirm"><input ref={selectAll} type="checkbox" aria-label="全选本批年级异常审批" disabled={busy}
        checked={rows.length > 0 && selected === rows.length} onChange={e => onCheckedChange({ ...checked, ...Object.fromEntries(rows.map(row => [row.student_id, e.target.checked])) })} />全选本批审批（含所有分页）</label>
      <span>已勾选 {selected} / {rows.length} 人</span>
    </div>
    <Table paginate headers={["姓名 / 账号", "原年级 → 目标年级", "核实依据（必填）", "审批"]}>
      {rows.map(row => <tr key={row.student_id}>
        <td>{row.name}<small>{row.account}</small></td>
        <td>{row.before || "无可比记录"} → {row.after}<small>{row.message}</small></td>
        <td><input className="student-anomaly-note" aria-label={`${row.name}年级异常依据`} aria-required="true"
          aria-invalid={!notes[row.student_id]?.trim()} aria-describedby={`${hintId} ${statusId}`} disabled={busy}
          value={notes[row.student_id] || ""} maxLength={500} placeholder="必填：本次年级变动的核实依据"
          onChange={e => { onNotesChange({ ...notes, [row.student_id]: e.target.value }); onCheckedChange({ ...checked, [row.student_id]: false }); }} /></td>
        <td><label className="teacher-confirm"><input type="checkbox" disabled={busy} checked={!!checked[row.student_id]}
          onChange={e => onCheckedChange({ ...checked, [row.student_id]: e.target.checked })} />已复核并审批通过</label></td>
      </tr>)}
    </Table>
    <p id={statusId} role="status" className={`teacher-alert teacher-alert--${missing.length || unchecked ? "warn" : "ok"}`}>
      {missing.length || unchecked
        ? `尚有 ${missing.length} 人未填写核实依据、${unchecked} 人未勾选审批，补齐后可进入预览。`
        : `本批 ${rows.length} 人均已填写依据并勾选审批，可保存审批并进入预览。`}
    </p>
  </div>;
}
