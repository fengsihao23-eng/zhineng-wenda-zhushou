import { useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useJsonQuery } from "../../hooks/useApi";
import { ErrorDisplay } from "../../components/ErrorDisplay";
import { getUserInfo } from "../../utils/auth";
import { apiFetch, apiError } from "../../services/api";
import { BASE, type Row, type PageData, Table, Pager, Badge, QueryState, canWrite, useAction, ActionError, fileBase64, HelpTip, usePagination, useClientPagination } from "./shared";
import "./teacher-workbench.css";

const columns = ["学校编号", "学校名称", "部门名称", "教师姓名", "性别", "教师账号", "学工号", "mac地址", "SN码", "状态", "说明", "身份证", "手机号码", "短号", "座机号", "电子邮箱", "备注", "任课年级班级", "班主任年级班级", "教研组长负责年级科目", "年级长负责年级", "是否教务主任", "是否校长", "是否总务主任"];
const roleNames: Record<string, string> = { TEACHER: "任课教师", HOMEROOM_TEACHER: "班主任", SUBJECT_LEADER: "教研组长", GRADE_LEADER: "年级长", PRINCIPAL: "校长", ACADEMIC_DIRECTOR: "教务主任", GENERAL_DIRECTOR: "总务主任", SCHOOL_VIEWER: "全校数据查看", SCHOOL_ADMIN: "学校管理员", EXAM_ADMIN: "考试管理员" };
const reasons = [
  { value: "depart", label: "离职", hint: "纯删除，删除后结束；复职走「导入教师」新增" },
  { value: "disable", label: "停用", hint: "纯删除，删除后结束" },
  { value: "incorrect", label: "错导入纠错", hint: "纯删除，该教师系错导入，后续不再导入" },
  { value: "change", label: "变更前删除", hint: "删除后建立绑定原教师ID的专属变更任务，更新文件须在任务内导入" },
  { value: "other", label: "其他", hint: "纯删除，须填写说明" },
];
const reasonName = (value: string) => reasons.find(row => row.value === value)?.label || "历史删除";
const maskedPhone = (value: string) => /^1\d{10}$/.test(value) ? `${value.slice(0, 3)}****${value.slice(-4)}` : value || "—";
const time = (value?: string) => value ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "—";

export function TeacherDialog({ title, drawer = false, busy = false, onClose, children, footer }: { title: string; drawer?: boolean; busy?: boolean; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const heading = useId();
  useLayoutEffect(() => { if (!ref.current?.open) ref.current?.showModal(); }, []);
  return <dialog ref={ref} className={`teacher-dialog ${drawer ? "teacher-dialog--drawer" : "teacher-dialog--modal"}`} aria-labelledby={heading}
    onClose={onClose} onCancel={event => { if (busy) event.preventDefault(); }} onClick={event => {
      if (busy || event.target !== ref.current) return;
      const bounds = ref.current.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) ref.current.close();
    }}>
    <header className="teacher-dialog__head"><h2 id={heading}>{title}</h2><button type="button" aria-label={`关闭${title}`} disabled={busy} onClick={() => ref.current?.close()}>×</button></header>
    <div className="teacher-dialog__body">{children}</div>
    {footer && <footer className="teacher-dialog__foot">{footer}</footer>}
  </dialog>;
}

export function Download({ path, filename, children }: { path: string; filename: string; children: ReactNode }) {
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  return <><button type="button" disabled={busy} onClick={async () => {
    setBusy(true); setError(null);
    try {
      const response = await apiFetch(`${BASE}${path}`);
      if (!response.ok) throw await apiError(response, "下载失败");
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e as Error); } finally { setBusy(false); }
  }}>{busy ? "准备下载…" : children}</button><ErrorDisplay error={error} /></>;
}

function Snapshot({ fields, name, id }: { fields: Record<string, string>; name: string; id: string }) {
  return <div className="teacher-snapshot"><div className="teacher-snapshot__title"><strong>{name}</strong><span className="teacher-id">教师ID：{id}</span></div>
    <dl className="teacher-field-grid">{columns.map(field => <div key={field}><dt>{field}</dt><dd>{fields[field] || "—"}</dd></div>)}</dl>
  </div>;
}

export function Steps({ labels, step }: { labels: string[]; step: number }) {
  return <ol className="teacher-steps" aria-label="办理进度">{labels.map((label, index) => <li key={label} aria-current={index + 1 === step ? "step" : undefined} className={index + 1 === step ? "active" : index + 1 < step ? "done" : ""}>{index + 1}. {label}</li>)}</ol>;
}

export function TeacherWorkbench() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [className, setClassName] = useState("");
  const pagination = usePagination(`${search}:${className}`);
  const selectionKey = `${search}:${className}:${pagination.page}:${pagination.pageSize}`;
  const [selection, setSelection] = useState<{ key: string; rows: Row[] }>({ key: "", rows: [] });
  useLayoutEffect(() => { setSelection({ key: selectionKey, rows: [] }); }, [selectionKey]);
  const chosen = selection.key === selectionKey ? selection.rows : [];
  const [archive, setArchive] = useState<Row | null>(null);
  const [deleting, setDeleting] = useState<Row[] | null>(null);
  const [notice, setNotice] = useState("");
  const query = useJsonQuery<PageData>(`${BASE}/roster/teachers/records?${new URLSearchParams({ search, class_name: className, page: String(pagination.page), page_size: String(pagination.pageSize) })}`);
  const visible = (query.data?.items || []).filter(row => row.id !== getUserInfo()?.user_id);
  const checkbox = useRef<HTMLInputElement>(null);
  const checkedAll = !!visible.length && visible.every(row => chosen.some(item => item.id === row.id));
  useLayoutEffect(() => { if (checkbox.current) checkbox.current.indeterminate = chosen.length > 0 && !checkedAll; }, [chosen.length, checkedAll]);
  const view = params.get("teacher_view") || "";
  const batchId = params.get("teacher_batch") || "";
  const taskId = params.get("teacher_task") || "";
  const open = (next: string, id = "") => {
    const values = new URLSearchParams(params);
    values.set("tab", "teachers"); values.set("teacher_view", next);
    values.delete("teacher_batch"); values.delete("teacher_task");
    if (next === "batch") values.set("teacher_batch", id);
    if (next === "task") values.set("teacher_task", id);
    setParams(values);
  };
  const close = () => {
    const values = new URLSearchParams(params);
    ["teacher_view", "teacher_batch", "teacher_task"].forEach(key => values.delete(key));
    setParams(values, { replace: true });
  };
  return <section className="teacher-workbench" aria-label="教师档案">
    <div className="teacher-list-bar">
      <div className="teacher-list-bar__title"><h2>教师信息列表</h2><HelpTip label="档案维护说明"><Table headers={["办理事项", "页面入口"]}><tr><td>新增教师</td><td>右上角「导入教师」</td></tr><tr><td>删除已有教师或变更资料</td><td>列表行「删除」；批量办理使用顶部「批量删除」</td></tr></Table><p>教师ID为平台统一分配的8～10位数字，仅用于数据关联和检索，与登录账号独立。资料变更沿用原ID；纯删除后新增分配新ID。</p><p>资料变更请选择「变更前删除」，再在专属任务内上传更新文件。</p></HelpTip><span className="teacher-muted">共 {query.data?.total ?? "—"} 条</span></div>
      <div className="teacher-actions">{canWrite() && <button disabled={!chosen.length} onClick={() => setDeleting(chosen)}>批量删除{chosen.length ? `（${chosen.length}）` : ""}</button>}<button onClick={() => open("records")}>操作记录</button>{canWrite() && <button className="teacher-primary" onClick={() => open("import")}>导入教师</button>}</div>
    </div>
    <div className="teacher-filters"><input aria-label="教师关键词" placeholder="关键词：教师ID / 姓名 / 登录账号 / 手机号" maxLength={100} value={search} onChange={e => setSearch(e.target.value)} /><input aria-label="教师班级筛选" placeholder="任课班级 / 年级.班级" maxLength={100} value={className} onChange={e => setClassName(e.target.value)} /></div>
    {notice && <p role="status" className="teacher-alert teacher-alert--ok">{notice}</p>}
    <QueryState query={query} empty={!query.data?.items.length}>
      <div className="data-table-wrap"><table className="data-table teacher-table"><thead><tr>
        {canWrite() && <th className="teacher-check"><input type="checkbox" ref={checkbox} aria-label="选择本页全部教师" checked={checkedAll} disabled={!visible.length || query.isFetching} onChange={e => setSelection({ key: selectionKey, rows: e.target.checked ? visible : [] })} /></th>}
        <th>姓名 / 登录账号</th><th>教师ID</th><th>原表任课班级</th><th>手机号 / 职务</th><th>操作</th>
      </tr></thead><tbody>{query.data?.items.map(row => <tr key={row.id}>
        {canWrite() && <td className="teacher-check"><input type="checkbox" aria-label={`选择教师${row.name}`} disabled={row.id === getUserInfo()?.user_id || query.isFetching} checked={chosen.some(item => item.id === row.id)} onChange={e => setSelection({ key: selectionKey, rows: e.target.checked ? [...chosen, row] : chosen.filter(item => item.id !== row.id) })} /></td>}
        <td><strong>{row.name}</strong><small>{row.username}</small></td><td title="平台唯一ID，与登录账号独立">{row.platform_id}</td><td>{row.class_name || "—"}</td><td>{maskedPhone(row.phone || "")}<small>{(row.duties || []).filter((d: string) => d !== "SCHOOL_VIEWER").map((d: string) => roleNames[d] || d).join("、")}</small></td>
        <td><div className="teacher-row-actions"><button onClick={() => setArchive(row)}>查看档案</button>{canWrite() && <button className="teacher-danger" disabled={row.id === getUserInfo()?.user_id} onClick={() => setDeleting([row])}>删除</button>}</div></td>
      </tr>)}</tbody></table></div>
    </QueryState>
    {query.data && !query.error && <Pager {...pagination} total={query.data.total} />}
    {archive && <TeacherDialog title="教师档案详情" drawer onClose={() => setArchive(null)} footer={<><button onClick={() => setArchive(null)}>关闭</button>{canWrite() && <button className="teacher-danger" disabled={archive.id === getUserInfo()?.user_id} onClick={() => { setDeleting([archive]); setArchive(null); }}>删除该教师</button>}</>}><Snapshot fields={archive.fields || {}} name={archive.name} id={archive.platform_id} /></TeacherDialog>}
    {deleting && <DeleteTeachers rows={deleting} onClose={() => setDeleting(null)} onDone={result => { setSelection({ key: selectionKey, rows: [] }); setNotice(result.message); }} onTask={id => { setDeleting(null); open("task", id); }} />}
    {(view === "records" || view === "deletions") && <OperationRecords initialTab={view === "deletions" ? "deletions" : "imports"} onClose={close} onBatch={id => open("batch", id)} onTask={id => open("task", id)} />}
    {view === "import" && <ImportWizard onClose={close} onComplete={() => { setNotice("教师导入已完成，列表已更新。"); }} />}
    {view === "batch" && batchId && <BatchReceipt id={batchId} onClose={close} onTask={id => open("task", id)} />}
    {view === "task" && taskId && <ChangeTask id={taskId} onClose={close} />}
  </section>;
}

function DeleteTeachers({ rows, onClose, onDone, onTask }: { rows: Row[]; onClose: () => void; onDone: (row: Row) => void; onTask: (id: string) => void }) {
  const action = useAction();
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [verified, setVerified] = useState(false);
  const [done, setDone] = useState<Row | null>(null);
  return <TeacherDialog title="删除教师档案" drawer busy={action.isPending} onClose={onClose} footer={done ? <button onClick={onClose}>关闭</button> : <><button disabled={action.isPending} onClick={onClose}>取消</button><button className="teacher-primary" disabled={!verified || !reason || (reason === "other" && !note.trim()) || action.isPending} onClick={() => action.mutate({ path: "/roster/teachers/delete", body: { teacher_ids: rows.map(row => row.id), reason, reason_note: note, confirmed: true } }, { onSuccess: result => { setDone(result); onDone(result); } })}>{action.isPending ? "正在删除…" : "确认删除"}</button></>}>
    <Steps labels={["核对原档案与删除原因", "确认删除"]} step={done ? 2 : 1} />
    {done ? <><div role="status" className="teacher-alert teacher-alert--ok"><strong>{done.task_id ? "原记录已删除并留存快照" : "删除完成"}</strong><p>{done.message}</p><p>原教师ID与删除快照长期保留，可在「操作记录 → 删除快照」查询。</p>{done.task_id && <p>专属变更任务：<span className="teacher-id">{done.task_id}</span>。导入失败或取消提交均保留任务。</p>}</div>{done.task_id && <div className="teacher-nav"><button onClick={onClose}>稍后继续</button><button className="teacher-primary" onClick={() => onTask(done.task_id)}>立即上传更新文件</button></div>}</> : <>
      {rows.length === 1 ? <Snapshot fields={rows[0].fields || {}} name={`${rows[0].name}（${rows[0].username}） · 原档案 24 列快照`} id={rows[0].platform_id} /> : <div className="teacher-snapshot"><strong>已选择 {rows.length} 名教师</strong><p className="teacher-muted">逐条展开查看快照，核对完整 24 列信息。</p>{rows.map(row => <details className="teacher-batch-snapshot" key={row.id}><summary>{row.name} / {row.username} · 查看快照</summary><Snapshot fields={row.fields || {}} name={row.name} id={row.platform_id} /></details>)}</div>}
      <fieldset className="teacher-reasons"><legend>删除原因（必选，将随快照留痕）</legend>{reasons.map(row => <label key={row.value}><input type="radio" name="teacher-deletion-reason" value={row.value} checked={reason === row.value} onChange={() => { setReason(row.value); setVerified(false); }} /><span>{row.label}<small>{row.hint}</small></span></label>)}{reason === "other" && <input aria-label="其他删除说明" placeholder="填写删除说明（必填）" maxLength={500} value={note} onChange={e => setNote(e.target.value)} />}</fieldset>
      <div className="teacher-alert teacher-alert--warn">删除后原账号即刻释放；原教师ID、24 列快照与历史关联长期保留。变更前删除须在专属任务内重导。</div>
      <label className="teacher-confirm"><input type="checkbox" checked={verified} onChange={e => setVerified(e.target.checked)} />我已核对原档案信息和删除原因，确认删除真实、准确。</label><ActionError action={action} />
    </>}
  </TeacherDialog>;
}

function FileUpload({ onUpload, taskId, onUploaded }: { onUpload?: ReactNode; taskId?: string; onUploaded: (batch: Row) => void }) {
  const upload = useAction();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [reading, setReading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const busy = reading || upload.isPending;
  const pick = (next: File | null) => {
    setError(null); upload.reset();
    if (next && (!/\.(xlsx|xls)$/i.test(next.name) || next.size > 5_000_000)) { setFile(null); setError(new Error(next.size > 5_000_000 ? "Excel 最大 5 MB、5000 行，请拆分文件。" : "仅支持 .xlsx / .xls 文件，请重新选择。")); return; }
    setFile(next);
  };
  return <section className="teacher-upload">
    {onUpload}
    <button type="button" className={`teacher-drop${dragging ? " is-dragging" : ""}`} disabled={busy || !canWrite()} onClick={() => input.current?.click()} onDragOver={e => { e.preventDefault(); if (!busy && canWrite()) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); if (!busy && canWrite()) pick(e.dataTransfer.files[0] || null); }}><strong>点击或拖拽上传</strong><span>《{taskId ? "教师变更原档案（含教师ID）" : "教师资料模板"}.xlsx》</span><small>{taskId ? "25 列＝24 列模板＋系统教师ID，教师ID为锁定字段，不可修改" : "24 列，列名与列顺序须与模板完全一致；教师账号须填写完整手机号"}</small></button>
    <input ref={input} aria-label="上传教师 Excel" type="file" accept=".xlsx,.xls" disabled={busy || !canWrite()} onChange={e => { pick(e.target.files?.[0] || null); e.target.value = ""; }} />
    {file && <div className="teacher-file"><span><strong>{file.name}</strong> · {(file.size / 1024).toFixed(1)} KB</span><button type="button" disabled={busy} onClick={() => pick(null)}>移除重选</button></div>}
    <p className="teacher-muted">支持 .xlsx / .xls，最大 5 MB、5000 行。手机号码可留空或包含 * 等脱敏字符，按原值保存；教师账号须填写完整的 11 位手机号。</p>
    <ErrorDisplay error={error} /><ActionError action={upload} />
    <div className="teacher-nav">{!taskId && <Download path="/roster/teachers/template" filename="教师资料模板.xlsx">下载《教师资料模板.xlsx》</Download>}<button type="button" className="teacher-primary" disabled={!file || busy || !canWrite()} onClick={async () => {
      if (!file || busy) return;
      setReading(true); setError(null);
      try {
        const content = await fileBase64(file);
        upload.mutate({ path: taskId ? `/roster/teachers/change-tasks/${taskId}/imports` : "/roster/teachers/imports", body: { filename: file.name, content_base64: content } }, { onSuccess: onUploaded });
      } catch (e) { setError(e as Error); } finally { setReading(false); }
    }}>{busy ? "正在预校验…" : "开始预校验"}</button></div>
  </section>;
}

function Issues({ batch }: { batch: Row }) {
  return <><div className="teacher-alert teacher-alert--error" role="alert"><strong>校验失败，整批退回</strong><p>本次未写入任何档案。请修正全部错误后整表重新上传。{batch.change_task_id && "专属变更任务已保留，旧档案不会自动恢复。"}</p></div><Table paginate headers={["行号 / 位置", "教师姓名 / 账号", "错误字段", "错误原因"]}>{batch.report.issues.map((issue: Row, index: number) => <tr key={index}><td>{issue.row_number ? `第 ${issue.row_number} 行` : "文件整体"}</td><td>{issue.name}<small>{issue.account}</small></td><td>{issue.fields}</td><td>{issue.message}<small>{issue.suggestion}</small></td></tr>)}</Table><div className="teacher-nav"><Download path={`/roster/imports/${batch.id}/errors`} filename="教师导入错误明细.xlsx">下载错误明细</Download></div></>;
}

function Duplicates({ batch, reviewed, onReview, decisions, onDecision, task = false }: { batch: Row; reviewed: Record<number, boolean>; onReview: (values: Record<number, boolean>) => void; decisions: Record<number, boolean>; onDecision: (values: Record<number, boolean>) => void; task?: boolean }) {
  const rows = batch.report.suspicious || [];
  if (!rows.length) return <div className="teacher-alert teacher-alert--ok">未发现疑似重复教师。{task ? "请继续核实新旧对应关系。" : "可确认整批入库。"}</div>;
  return <section aria-label="疑似重复教师确认"><h3>疑似重复{task ? "提醒" : "清单"}</h3><p className="teacher-muted">按教师姓名＋任课年级班级整格文本完全一致比对；任课信息为空者不参与。{task ? "仅提醒核对，不提供单行放弃。" : "命中行默认保留，须逐条确认保留或放弃，放弃行不入库。"}</p><Table paginate headers={["Excel 行号", "新行内容", "命中已有教师", ...(task ? [] : ["保留 / 放弃"]), "确认"]}>{rows.map((row: Row) => <tr key={row.row_number}><td>{row.row_number}</td><td>{row.name}<small>{row.account}</small><small>{row.teaching}</small></td><td>{row.matches.map((m: Row) => <div key={m.id}>{m.name} / {m.account}<small>{m.teaching || (m.subjects_grades || []).join("、")}</small></div>)}</td>{!task && <td><select aria-label={`第${row.row_number}行保留或放弃`} disabled={!canWrite()} value={String(decisions[row.row_number] ?? true)} onChange={e => { onDecision({ ...decisions, [row.row_number]: e.target.value === "true" }); onReview({ ...reviewed, [row.row_number]: false }); }}><option value="true">保留（默认）</option><option value="false">放弃</option></select></td>}<td><label className="teacher-confirm"><input type="checkbox" disabled={!canWrite()} checked={!!reviewed[row.row_number]} onChange={e => onReview({ ...reviewed, [row.row_number]: e.target.checked })} />已核对第 {row.row_number} 行</label></td></tr>)}</Table></section>;
}

function ImportWizard({ onClose, onComplete }: { onClose: () => void; onComplete: () => void }) {
  const [step, setStep] = useState(1);
  const [batch, setBatch] = useState<Row | null>(null);
  const [decisions, setDecisions] = useState<Record<number, boolean>>({});
  const [reviewed, setReviewed] = useState<Record<number, boolean>>({});
  const action = useAction();
  const refresh = async () => {
    if (!batch) return;
    const response = await apiFetch(`${BASE}/roster/imports/${batch.id}`);
    if (response.ok) { const next = await response.json(); setBatch(next); if (!next.report.ok) setStep(2); }
  };
  const reset = () => { setStep(1); setBatch(null); setDecisions({}); setReviewed({}); action.reset(); };
  return <TeacherDialog title="导入教师（Excel 批量新增）" busy={action.isPending} onClose={onClose}>
    <Steps labels={["上传文件", "预校验与错误清单", "疑似重复确认与回执"]} step={step} />
    {step === 1 && <FileUpload onUploaded={row => { setBatch(row); setStep(2); }} />}
    {step === 2 && batch && <>{batch.report.ok ? <><div className="teacher-alert teacher-alert--ok">预校验通过，共 {batch.report.total_rows} 行。尚未写入任何档案。</div><div className="teacher-alert teacher-alert--warn">离职 / 停用请在列表「删除」办理。资料变更请选择「变更前删除」，使用专属任务。</div><div className="teacher-nav"><button onClick={reset}>重新上传</button><button className="teacher-primary" onClick={() => setStep(3)}>下一步：疑似重复确认</button></div></> : <><Issues batch={batch} /><div className="teacher-nav"><button onClick={reset}>重新上传</button></div></>}</>}
    {step === 3 && batch && (batch.status === "succeeded" ? <Receipt batch={batch} /> : <><Duplicates batch={batch} reviewed={reviewed} onReview={setReviewed} decisions={decisions} onDecision={setDecisions} /><details className="teacher-preview"><summary>查看原始资料（24 列）</summary><RowsPreview batch={batch} /></details><p className="teacher-muted">新教师将生成独立教师ID。初始密码＝教师账号，首次登录强制修改；角色按结构化任课与职务字段生成。</p><ActionError action={action} /><div className="teacher-nav"><button disabled={action.isPending} onClick={reset}>重新上传</button><button className="teacher-primary" disabled={!canWrite() || action.isPending || (batch.report.suspicious || []).some((row: Row) => !reviewed[row.row_number])} onClick={() => action.mutate({ path: `/roster/imports/${batch.id}/confirm`, body: { expected_revision: batch.revision, duplicate_decisions: Object.fromEntries((batch.report.suspicious || []).map((row: Row) => [row.row_number, decisions[row.row_number] ?? true])) } }, { onSuccess: row => { setBatch(row); onComplete(); }, onError: () => { void refresh(); } })}>{action.isPending ? "正在整批入库…" : "确认入库"}</button></div></>)}
  </TeacherDialog>;
}

function RowsPreview({ batch }: { batch: Row }) {
  const pagination = useClientPagination<Row>(batch.rows || []);
  return <><Table headers={["Excel 行号", ...batch.columns]}>{pagination.items.map(row => <tr key={row.row_number}><td>{row.row_number}</td>{batch.columns.map((field: string) => <td key={field}>{row.values[field] || "—"}</td>)}</tr>)}</Table><Pager {...pagination} /></>;
}

function Receipt({ batch }: { batch: Row }) {
  const report = batch.report;
  return <section aria-label="导入回执"><div className="teacher-alert teacher-alert--ok" role="status"><h3>{batch.change_task_id ? "变更任务已完成" : "导入完成"}</h3><p>成功 {report.success_count} 条 · 主动放弃 {report.skipped_count || 0} 条{batch.change_task_id && " · 沿用原教师ID"}</p><p>操作人：{report.confirmed_by_name} · {time(report.confirmed_at)}</p><p>批次号：{batch.id}</p>{(report.skipped_rows || []).length > 0 && <p>放弃的 Excel 行号：{report.skipped_rows.join("、")}</p>}</div>{report.versions && <VersionChanges versions={report.versions} />}<details className="teacher-preview"><summary>查看导入明细（{report.total_rows} 行）</summary><RowsPreview batch={batch} /></details>{batch.has_original && <Download path={`/roster/imports/${batch.id}/original`} filename={batch.filename}>下载原文件</Download>}</section>;
}

function VersionChanges({ versions }: { versions: Row[] }) {
  return <Table paginate headers={["原教师ID / 新行", "变更字段", "变更前", "变更后"]}>{versions.flatMap(version => version.changes.length ? version.changes.map((change: Row) => <tr key={`${version.teacher_id}:${change.field}`}><td>{version.platform_id || "—"}<small>第 {version.row_number} 行</small></td><td>{change.field}</td><td>{change.before || "—"}</td><td className="teacher-changed">{change.after || "—"}</td></tr>) : [<tr key={version.teacher_id}><td>{version.platform_id || "—"}</td><td colSpan={3}>资料字段未变更</td></tr>])}</Table>;
}

function OperationRecords({ initialTab, onClose, onBatch, onTask }: { initialTab: string; onClose: () => void; onBatch: (id: string) => void; onTask: (id: string) => void }) {
  const [tab, setTab] = useState(initialTab);
  const [search, setSearch] = useState("");
  const [reason, setReason] = useState("");
  const [snapshot, setSnapshot] = useState<Row | null>(null);
  const pagination = usePagination(`${search}:${reason}`);
  const imports = useJsonQuery<PageData>(`${BASE}/roster/teachers/imports?${new URLSearchParams({ search, paginated: "true", page: String(pagination.page), page_size: String(pagination.pageSize) })}`, tab === "imports");
  const deletions = useJsonQuery<PageData>(`${BASE}/roster/teachers/deletions?${new URLSearchParams({ search, reason, page: String(pagination.page), page_size: String(pagination.pageSize) })}`, tab === "deletions");
  return <TeacherDialog title="操作记录" drawer onClose={onClose}>
    {snapshot ? <><div className="teacher-nav"><button onClick={() => setSnapshot(null)}>← 返回列表</button></div><p className="teacher-muted">{reasonName(snapshot.reason)} · {snapshot.reason_note} · {snapshot.operator_name} · {time(snapshot.deleted_at)}</p><Snapshot name={snapshot.teacher_name} id={snapshot.platform_id} fields={snapshot.fields} />{snapshot.updated_fields && <><h3>新旧资料版本对照</h3><VersionChanges versions={[{ id: snapshot.id, teacher_id: snapshot.user_id, platform_id: snapshot.platform_id, row_number: "—", changes: columns.filter(field => snapshot.fields[field] !== snapshot.updated_fields[field]).map(field => ({ field, before: snapshot.fields[field], after: snapshot.updated_fields[field] })) }]} /></>}</> : <>
      <div className="teacher-record-tabs" role="tablist" aria-label="操作记录类型"><button role="tab" aria-selected={tab === "imports"} className={tab === "imports" ? "active" : ""} onClick={() => { setTab("imports"); setSearch(""); }}>导入回执</button><button role="tab" aria-selected={tab === "deletions"} className={tab === "deletions" ? "active" : ""} onClick={() => { setTab("deletions"); setSearch(""); }}>删除快照（含变更任务）</button></div>
      <div className="teacher-filters"><input aria-label="操作记录关键词" placeholder={`搜索：教师姓名 / 账号 / 批次号 / ${tab === "deletions" ? "任务号 / " : ""}文件名`} maxLength={100} value={search} onChange={e => setSearch(e.target.value)} />{tab === "deletions" && <select aria-label="删除原因筛选" value={reason} onChange={e => setReason(e.target.value)}><option value="">全部原因</option>{reasons.map(row => <option key={row.value} value={row.value}>{row.label}</option>)}</select>}</div>
      {tab === "imports" ? <QueryState query={imports} empty={!imports.data?.items.length}>{imports.data?.items.map(row => <article className="teacher-record" key={row.id}><div className="teacher-record__head"><strong>{row.change_task_id ? "变更任务导入" : "批量导入"}</strong><Badge value={row.status} /></div><p className="teacher-muted">批次 {row.id}</p><p className="teacher-muted">操作人：{row.operator_name} · {time(row.created_at)}</p><p>文件：{row.filename}</p>{row.status === "succeeded" && <p className="teacher-muted">成功 {row.report?.success_count ?? "—"} 条 · 放弃 {row.report?.skipped_count || 0} 条</p>}<div className="teacher-record__actions"><button onClick={() => onBatch(row.id)}>{row.status === "ready" ? "继续确认导入" : "查看导入明细"}</button>{row.has_original && <Download path={`/roster/imports/${row.id}/original`} filename={row.filename}>下载原文件</Download>}</div></article>)}{imports.data && !imports.error && <Pager {...pagination} total={imports.data.total} />}</QueryState> : <><QueryState query={deletions} empty={!deletions.data?.items.length}>{deletions.data?.items.map(row => <article className="teacher-record" key={row.id}><div className="teacher-record__head"><strong>{row.teacher_name}（{row.account}）</strong><span className="teacher-tag">{reasonName(row.reason)}</span></div><p className="teacher-muted">删除时间 {time(row.deleted_at)} · 删除人：{row.operator_name}</p>{row.reason_note && <p>{row.reason_note}</p>}<p className="teacher-muted">原教师ID：{row.platform_id}</p>{row.operation_id && <p className="teacher-muted">批次：{row.operation_id}</p>}{row.task_id && <><p className="teacher-muted">任务：{row.task_id}</p><p className="teacher-muted">{row.task_status === "succeeded" ? `任务已完成 · ${time(row.reimported_at)}` : "任务进行中，失败或取消均可继续"}</p></>}<div className="teacher-record__actions"><button onClick={() => setSnapshot(row)}>查看 24 列快照</button>{row.updated_fields && <button onClick={() => setSnapshot(row)}>新旧资料版本对照</button>}{row.task_id && <button className={row.task_status === "pending" ? "teacher-primary" : ""} onClick={() => onTask(row.task_id)}>{row.task_status === "pending" && canWrite() ? "继续变更任务" : "查看任务详情"}</button>}</div></article>)}</QueryState>{deletions.data && !deletions.error && <Pager {...pagination} total={deletions.data.total} />}</>}
    </>}
  </TeacherDialog>;
}

function BatchReceipt({ id, onClose, onTask }: { id: string; onClose: () => void; onTask: (id: string) => void }) {
  const query = useJsonQuery<Row>(`${BASE}/roster/imports/${id}`);
  return <TeacherDialog title="导入批次详情" onClose={onClose}><QueryState query={query}>{query.data && (query.data.change_task_id ? <><p>该批次属于专属变更任务，请在任务内核对身份和变更资料。</p><button onClick={() => onTask(query.data!.change_task_id)}>查看变更任务</button>{query.data.status === "succeeded" && <Receipt batch={query.data} />}{!query.data.report.ok && <Issues batch={query.data} />}</> : <ExistingImport batch={query.data} onRefresh={() => { void query.refetch(); }} />)}</QueryState></TeacherDialog>;
}

function ExistingImport({ batch, onRefresh }: { batch: Row; onRefresh: () => void }) {
  const action = useAction();
  const [decisions, setDecisions] = useState<Record<number, boolean>>({});
  const [reviewed, setReviewed] = useState<Record<number, boolean>>({});
  if (batch.status === "succeeded") return <Receipt batch={batch} />;
  if (!batch.report.ok || batch.status !== "ready") return <Issues batch={batch} />;
  return <><p>{batch.filename} · 共 {batch.report.total_rows} 行，尚未写入档案。</p><Duplicates batch={batch} reviewed={reviewed} onReview={setReviewed} decisions={decisions} onDecision={setDecisions} /><RowsPreview batch={batch} /><ActionError action={action} /><div className="teacher-nav"><button className="teacher-primary" disabled={!canWrite() || action.isPending || (batch.report.suspicious || []).some((row: Row) => !reviewed[row.row_number])} onClick={() => action.mutate({ path: `/roster/imports/${batch.id}/confirm`, body: { expected_revision: batch.revision, duplicate_decisions: Object.fromEntries((batch.report.suspicious || []).map((row: Row) => [row.row_number, decisions[row.row_number] ?? true])) } }, { onSuccess: onRefresh, onError: onRefresh })}>{action.isPending ? "正在整批入库…" : "确认入库"}</button></div></>;
}

function ChangeTask({ id, onClose }: { id: string; onClose: () => void }) {
  const query = useJsonQuery<Row>(`${BASE}/roster/teachers/change-tasks/${id}`);
  return query.data && !query.error ? <ChangeTaskWizard key={id} task={query.data} onClose={onClose} onRefresh={() => { void query.refetch(); }} /> : <TeacherDialog title="教师专属变更任务" onClose={onClose}><QueryState query={query}>{null}</QueryState></TeacherDialog>;
}

function ChangeTaskWizard({ task, onClose, onRefresh }: { task: Row; onClose: () => void; onRefresh: () => void }) {
  const [step, setStep] = useState(1);
  const [batch, setBatch] = useState<Row | null>(() => task.status === "succeeded" ? task.batches.find((row: Row) => row.status === "succeeded") || null : null);
  const [mapping, setMapping] = useState<Record<number, string>>({});
  const [identity, setIdentity] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [reviewed, setReviewed] = useState<Record<number, boolean>>({});
  const [localError, setLocalError] = useState<Error | null>(null);
  const action = useAction();
  const snapshots: Row[] = task.snapshots;
  const completed = batch?.status === "succeeded" ? batch : task.status === "succeeded" ? task.batches.find((row: Row) => row.status === "succeeded") : null;
  const reset = () => { setStep(1); setBatch(null); setIdentity(false); setConfirmed(false); setMapping({}); setReviewed({}); setLocalError(null); action.reset(); };
  const allReviewed = !!batch && (batch.report.suspicious || []).every((row: Row) => reviewed[row.row_number]);
  const verifyMapping = () => {
    if (!batch) return;
    const errors: string[] = [];
    const chosen = new Set<string>();
    for (const row of batch.rows) {
      const value = mapping[row.row_number];
      if (!value) errors.push(`第 ${row.row_number} 行：未指定原教师`);
      else if (chosen.has(value)) errors.push(`第 ${row.row_number} 行：原教师重复关联`);
      else if (![value, snapshots.find(snapshot => snapshot.platform_id === value)?.user_id].includes(row.values["教师ID"])) errors.push(`第 ${row.row_number} 行：对应教师与锁定教师ID不一致`);
      chosen.add(value);
    }
    if (!identity) errors.push("尚未核实对应关系身份");
    if (chosen.size !== snapshots.length) errors.push("须覆盖任务内全部原教师");
    if (errors.length) { setLocalError(new Error(errors.join("；"))); return; }
    setLocalError(null); setConfirmed(false); setStep(4);
  };
  const versions = batch ? batch.rows.map((row: Row) => {
    const original = snapshots.find(snapshot => snapshot.platform_id === mapping[row.row_number]);
    return { id: String(row.row_number), teacher_id: original?.user_id, platform_id: original?.platform_id, row_number: row.row_number, changes: columns.filter(field => (original?.fields[field] || "") !== row.values[field]).map(field => ({ field, before: original?.fields[field] || "", after: row.values[field] })) };
  }) : [];
  return <TeacherDialog title="教师专属变更任务" busy={action.isPending} onClose={onClose} footer={<><button disabled={action.isPending} onClick={onClose}>{task.status === "succeeded" || batch?.status === "succeeded" ? "关闭" : "取消（保留任务）"}</button><span className="teacher-muted">{task.status === "succeeded" || batch?.status === "succeeded" ? "任务已完成" : "失败或取消提交均保留任务"}</span></>}>
    <p className="teacher-muted teacher-task-id">任务 {task.id} · 绑定原教师ID</p>
    {completed ? <Receipt batch={completed} /> : <>
      <Steps labels={["上传更新文件", "预校验与重复提醒", "指定对应关系", "预览变更并提交"]} step={step} />
      <ActionError action={action} />
      {step === 1 && <FileUpload taskId={task.id} onUploaded={row => { setBatch(row); setStep(2); if (snapshots.length === 1 && row.rows.length === 1) setMapping({ [row.rows[0].row_number]: snapshots[0].platform_id }); }} onUpload={<div className="teacher-snapshot"><div className="teacher-record__head"><strong>任务内原教师 {snapshots.length} 名</strong><Download path={`/roster/teachers/change-tasks/${task.id}/template`} filename="教师变更原档案（含教师ID）.xlsx">下载原档案（25 列）</Download></div>{snapshots.map(row => <p key={row.id}>{row.teacher_name} / {row.account}<small className="teacher-muted"> · 教师ID：{row.platform_id}</small></p>)}<p className="teacher-muted">请先下载任务原档案，在原文件上修改后上传；教师ID不可修改。更新行数须恰好等于 {snapshots.length} 行。</p>{(task.batches || []).find((row: Row) => row.status === "ready") && <button onClick={() => { const ready = task.batches.find((row: Row) => row.status === "ready"); setBatch(ready); setStep(2); if (snapshots.length === 1) setMapping({ [ready.rows[0].row_number]: snapshots[0].platform_id }); }}>继续上次预校验批次</button>}</div>} />}
      {step === 2 && batch && <>{!batch.report.ok ? <Issues batch={batch} /> : <><div className="teacher-alert teacher-alert--ok">预校验通过，共 {batch.report.total_rows} 行；尚未写入资料。</div><Duplicates task batch={batch} reviewed={reviewed} onReview={setReviewed} decisions={{}} onDecision={() => undefined} /></>}<div className="teacher-nav"><button onClick={reset}>重新上传</button>{batch.report.ok && <button className="teacher-primary" disabled={!allReviewed || !canWrite()} onClick={() => setStep(3)}>下一步：指定对应关系</button>}</div></>}
      {step === 3 && batch && <><p className="teacher-muted">{snapshots.length === 1 ? "单人单行任务已自动关联原教师。请核实新旧身份。" : "请逐行指定原教师，每名原教师只能关联一次，指定关系须与锁定教师ID一致。"}</p><Table paginate headers={["Excel 行号", "新姓名 / 账号 / 手机号码", "原姓名 / 账号 / 手机号码"]}>{batch.rows.map((row: Row) => <tr key={row.row_number}><td>{row.row_number}</td><td>{row.values["教师姓名"]}<small>{row.values["教师账号"]}</small><small>{row.values["手机号码"] || "—"}</small></td><td><select aria-label={`第${row.row_number}行原教师`} disabled={snapshots.length === 1 || !canWrite()} value={mapping[row.row_number] || ""} onChange={e => { setMapping({ ...mapping, [row.row_number]: e.target.value }); setIdentity(false); }}><option value="">请选择原教师</option>{snapshots.map(snapshot => <option key={snapshot.id} value={snapshot.platform_id}>{snapshot.teacher_name} / {snapshot.account} / 教师ID：{snapshot.platform_id}</option>)}</select></td></tr>)}</Table><label className="teacher-confirm"><input type="checkbox" checked={identity} onChange={e => setIdentity(e.target.checked)} />我已逐行核实对应关系身份真实、准确。</label><ErrorDisplay error={localError} /><div className="teacher-nav"><button onClick={() => setStep(2)}>上一步</button><button className="teacher-primary" onClick={verifyMapping}>下一步：预览变更</button></div></>}
      {step === 4 && batch && <><h3>预览对应关系与字段变更</h3><p className="teacher-muted">沿用原教师ID；账号按新值建立，密码重置为新账号，首次登录强制修改。</p><VersionChanges versions={versions} /><label className="teacher-confirm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />我已核对对应关系及全部变更内容，确认整批提交。</label><div className="teacher-nav"><button disabled={action.isPending} onClick={() => { setStep(3); setConfirmed(false); }}>上一步</button><button className="teacher-primary" disabled={!confirmed || action.isPending || !canWrite()} onClick={() => action.mutate({ path: `/roster/imports/${batch.id}/confirm`, body: { expected_revision: batch.revision, teacher_replacements: mapping, identity_confirmed: true, changes_confirmed: true, duplicate_decisions: Object.fromEntries((batch.report.suspicious || []).map((row: Row) => [row.row_number, true])) } }, { onSuccess: row => { setBatch(row); onRefresh(); }, onError: async () => {
      onRefresh();
      try {
        const response = await apiFetch(`${BASE}/roster/imports/${batch.id}`);
        if (response.ok) setBatch(await response.json());
      } catch { /* Keep the submission error visible if the refresh also fails. */ }
      setStep(2);
    } })}>{action.isPending ? "正在整批提交…" : "确认整批提交"}</button></div></>}
    </>}
  </TeacherDialog>;
}
