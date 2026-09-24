import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { AppShell } from "../../layouts/AppShell";
import { useJsonQuery } from "../../hooks/useApi";
import { apiFetch, apiError } from "../../services/api";
import { ErrorDisplay } from "../../components/ErrorDisplay";
import { DetailDialog } from "../../components/DetailDialog";
import { getUserInfo } from "../../utils/auth";
import { BASE, Row, PageData, Table, Pager, Badge, QueryState, canWrite, useAction, ActionError, fileBase64, FormPanel, options, HelpTip, usePagination, useClientPagination } from "./shared";

type Kind = "teachers" | "students";
const roleNames: Record<string, string> = { SCHOOL_ADMIN: "学校管理员", EXAM_ADMIN: "考试管理员", TEACHER: "任课教师", HOMEROOM_TEACHER: "班主任", SUBJECT_LEADER: "备课 / 教研组长", GRADE_LEADER: "年级长", PRINCIPAL: "校长", ACADEMIC_DIRECTOR: "教务主任", GENERAL_DIRECTOR: "总务主任", SCHOOL_VIEWER: "全校数据查看" };
const actionNames: Record<string, string> = { delete: "删除原档案", disable: "停用", depart: "离职", suspend: "休学", withdraw: "退学", graduate: "毕业归档" };

function activeBatchKey(kind: Kind): string {
  const user = getUserInfo();
  return `roster-active-batch:${user?.school_id || "unknown"}:${user?.user_id || "anonymous"}:${kind}`;
}

function savedBatch(key: string): string {
  try {
    const id = sessionStorage.getItem(key) || "";
    return /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id) ? id : "";
  } catch { return ""; }
}

function rememberBatch(key: string, id: string): void {
  try {
    if (id) sessionStorage.setItem(key, id);
    else sessionStorage.removeItem(key);
  } catch { /* Storage may be unavailable. */ }
}

function Download({ path, filename, children }: { path: string; filename: string; children: React.ReactNode }) {
  const [error, setError] = useState<Error | null>(null);
  const [pending, setPending] = useState(false);
  return <><button disabled={pending} onClick={async () => {
    setPending(true); setError(null);
    try {
      const response = await apiFetch(`${BASE}${path}`);
      if (!response.ok) throw await apiError(response, "下载失败");
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e as Error); } finally { setPending(false); }
  }}>{pending ? "准备下载…" : children}</button><ErrorDisplay error={error} /></>;
}

export function RosterWorkbench({ kind }: { kind: Kind }) {
  const teacher = kind === "teachers", noun = teacher ? "教师" : "学生";
  const [search, setSearch] = useState("");
  const [phone, setPhone] = useState("");
  const [className, setClassName] = useState("");
  const pagination = usePagination(JSON.stringify([search, phone, className]));
  const { page, pageSize } = pagination;
  const [selected, setSelected] = useState<Row | null>(null);
  const detailRef = useRef<HTMLDialogElement>(null);
  const [operation, setOperation] = useState<{ row: Row; action: string } | null>(null);
  const [notice, setNotice] = useState("");
  const action = useAction();
  const query = useJsonQuery<PageData>(`${BASE}/roster/${kind}/records?${new URLSearchParams({ search, phone, class_name: className, page: String(page), page_size: String(pageSize) })}`);
  useLayoutEffect(() => {
    if (selected && !detailRef.current?.open) detailRef.current?.showModal();
  }, [selected]);
  return <section className="roster-workbench">
    <div className="wb-toolbar wb-page-actions">
      <h2>{noun}信息列表</h2>
      <HelpTip label="档案维护说明">{noun}统一通过 Excel 导入。信息变更须先删除原档案，再修改模板重新导入。{teacher ? "删除保留完整快照，历史任教与成绩不变。" : "删除前检查关联数据；休学、退学、毕业归档会停用账号并保留历史。"}</HelpTip>
      <Link className="secondary-button" to={`/admin/school/${kind}/imports`}>导入记录及操作回执</Link>
      {teacher && <Link className="secondary-button" to="/admin/school/teachers/deletions">教师删除记录</Link>}
      {canWrite() && <Link className="primary-button" to={`/admin/school/${kind}/import`}>导入{noun}</Link>}
    </div>
    <div className="wb-toolbar">
      <input aria-label={`${noun}姓名或账号`} placeholder="姓名 / 账号" value={search} onChange={e => setSearch(e.target.value)} />
      {teacher && <input aria-label="教师手机号" placeholder="手机号" value={phone} onChange={e => setPhone(e.target.value)} />}
      <input aria-label={`${noun}班级筛选`} placeholder={teacher ? "任课班级 / 年级.班级" : "班级名称"} value={className} onChange={e => setClassName(e.target.value)} />
    </div>
    {notice && <p role="status" className="wb-status">{notice}</p>}
    {!operation && <ActionError action={action} />}
    {operation && <DetailDialog title="确认档案操作" busy={action.isPending} onClose={() => setOperation(null)}><section aria-label="确认档案操作">
      <ActionError action={action} />
      <h3>{actionNames[operation.action]}：{operation.row.name} / {operation.row.username}</h3>
      <p>{operation.action === "delete" ? (teacher ? "确认后原账号立即停止登录并释放账号名称，完整的 24 列资料、删除人和时间长期保留。历史任教与成绩不变；更新 Excel 后重新导入，原密码按规则沿用。" : "确认后删除原档案和对应登录账号。存在成绩、错题等关联时会拦截；删除成功后，须用更新后的 Excel 重新导入。") : "账号将立即停止访问，档案和历史成绩保留。"}</p>
      <div className="wb-toolbar"><button disabled={action.isPending} onClick={() => action.mutate({ path: `/roster/${kind}/records/${operation.row.id}/actions`, body: { action: operation.action, confirmed: true } }, { onSuccess: result => { setOperation(null); setSelected(null); setNotice(result.message); } })}>{action.isPending ? "处理中…" : `确认${actionNames[operation.action]}`}</button><button disabled={action.isPending} onClick={() => setOperation(null)}>取消</button></div>
    </section></DetailDialog>}
    {query.data && !query.error && <Pager {...pagination} total={query.data.total} />}
    <QueryState query={query} empty={!query.data?.items.length}>
      <Table headers={["姓名 / 登录账号", teacher ? "原表任课班级" : "班级", teacher ? "手机号 / 职务" : "学号", "状态", "操作"]}>
        {query.data?.items.map(row => <tr key={row.id}>
          <td><strong>{row.name}</strong><small className="subtle">{row.username || "待绑定账号"}{!teacher && row.user_id && " · 已绑定账号"}</small></td>
          <td>{row.class_name || row.fields?.["任课年级班级"] || "—"}</td>
          <td>{teacher ? <>{row.phone || "—"}<small className="subtle">{row.duties.map((d: string) => roleNames[d] || d).join("、")}</small></> : row.student_no || "—"}</td>
          <td><Badge value={row.status} /></td><td className="roster-actions"><button onClick={() => setSelected(row)}>查看档案</button>
            {canWrite() && <><button onClick={() => { action.reset(); setOperation({ row, action: "delete" }); }}>删除原档案</button>{row.status === "active" && (teacher ? <><button onClick={() => setOperation({ row, action: "disable" })}>停用</button><button onClick={() => setOperation({ row, action: "depart" })}>离职</button></> : <><button onClick={() => { action.reset(); setOperation({ row, action: "suspend" }); }}>休学</button><button onClick={() => { action.reset(); setOperation({ row, action: "withdraw" }); }}>退学</button><button onClick={() => setOperation({ row, action: "graduate" })}>毕业归档</button></>)}</>}
            {!teacher && row.status === "active" && <Link to={`/admin/students/${row.id}`}>查看学情</Link>}
          </td></tr>)}
      </Table>
    </QueryState>
    {selected && <dialog className="roster-detail-dialog" ref={detailRef} aria-labelledby={`roster-detail-title-${kind}`} onClose={() => setSelected(null)}><div className="wb-toolbar"><h3 id={`roster-detail-title-${kind}`}>{selected.name} · 档案详情</h3><button type="button" onClick={() => detailRef.current?.close()}>关闭档案</button></div><HelpTip label="信息变更说明">删除原档案后，修改统一 Excel 模板，重新上传并确认。</HelpTip><Table headers={["模板字段", "原始内容"]}>{Object.entries(selected.fields || {}).map(([key, value]) => <tr key={key}><td>{key}</td><td className="roster-value">{String(value || "—")}</td></tr>)}</Table>{!teacher && !selected.user_id && canWrite() && <LegacyAccountBinding key={`account-${selected.id}`} id={selected.id} />}</dialog>}
  </section>;
}

export function RosterTaskPage({ view }: { view: "import" | "history" | "batch" | "deletions" }) {
  const { kind = "teachers", batchId = "" } = useParams();
  if (kind !== "teachers" && kind !== "students") return <Navigate to="/admin/school" replace />;
  if (view === "deletions" && kind !== "teachers") return <Navigate to="/admin/school?tab=students" replace />;
  const noun = kind === "teachers" ? "教师" : "学生";
  const title = { import: `导入${noun}`, history: `${noun}导入记录及操作回执`, batch: "导入预览与结果", deletions: "教师删除记录" }[view];
  return <AppShell title={title} eyebrow={`师生班级与考试 / ${noun}档案`}>
    <div className="wb-toolbar">
      <Link className="secondary-button" to={`/admin/school?tab=${kind}`}>返回信息列表</Link>
      {view !== "history" && <Link to={`/admin/school/${kind}/imports`}>导入记录及操作回执</Link>}
      {view !== "import" && canWrite() && <Link className="primary-button" to={`/admin/school/${kind}/import`}>导入{noun}</Link>}
    </div>
    <section className="roster-workbench">
      {view === "import" && <RosterImport key={kind} kind={kind} />}
      {view === "history" && <RosterHistory key={kind} kind={kind} />}
      {view === "deletions" && <TeacherDeletionHistory />}
      {view === "batch" && <RosterBatch key={batchId} id={batchId} kind={kind} />}
    </section>
  </AppShell>;
}

function RosterImport({ kind }: { kind: Kind }) {
  const teacher = kind === "teachers", noun = teacher ? "教师" : "学生";
  const navigate = useNavigate();
  const upload = useAction();
  const history = useJsonQuery<Row[]>(`${BASE}/roster/${kind}/imports`);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<Error | null>(null);
  const [reading, setReading] = useState(false);
  const [slow, setSlow] = useState(false);
  const busy = reading || upload.isPending;
  const recent = history.data?.find(row => row.status === "ready" && (!file || row.filename === file.name));
  useEffect(() => {
    if (!busy) { setSlow(false); return; }
    const timer = window.setTimeout(() => setSlow(true), 15000);
    return () => window.clearTimeout(timer);
  }, [busy]);
  const previous = savedBatch(activeBatchKey(kind));
  return <section className="panel">
    <div className="wb-toolbar"><h2>上传{noun}资料</h2><HelpTip label="导入说明">
      <p>下载模板，替换样例后上传；预检通过并核对疑似重复记录后，确认入库。</p>
      <p>{teacher ? "教师模板 24 列，支持 .xlsx。账号只与教师比对，手机号原样保存，任教班级作为关联参考。" : "学生模板 30 列，支持 .xls / .xlsx。姓名、账号必填；状态仅接受「正常」，学号可留空。年级填写文本名称，班级号填写 N班。"}文件最大 5 MB、5000 行。</p>
      <p>信息变更须先删除原档案，再修改模板重新导入。{teacher && "重导沿用原密码；仍使用初始密码时，新密码等于新账号。更换账号时须指定对应删除记录。"}</p>
      <Download path={`/roster/${kind}/error-template`} filename={`${noun}错误清单模板.xlsx`}>下载错误清单模板（8 列）</Download>
    </HelpTip></div>
    <div className="wb-toolbar"><Download path={`/roster/${kind}/template`} filename={`${noun}资料模板.xlsx`}>下载{noun}资料模板（{teacher ? 24 : 30} 列）</Download>
      {previous && <Link to={`/admin/school/${kind}/imports/${previous}`}>继续查看上次批次</Link>}
    </div>
    {recent && <p className="wb-status">{file ? "该文件已有待确认批次" : "有待确认的导入批次"} · <Link to={`/admin/school/${kind}/imports/${recent.id}`}>查看预检结果</Link></p>}
    {canWrite() && <form className="wb-toolbar" onSubmit={async event => {
      event.preventDefault(); if (!file || busy) return;
      setReading(true); setFileError(null); upload.reset();
      try {
        if (file.size > 5_000_000) throw new Error("Excel 最大 5 MB、5000 行，请拆分文件。");
        const content = await fileBase64(file);
        upload.mutate({ path: `/roster/${kind}/imports?compact=true`, body: { filename: file.name, content_base64: content } }, { onSuccess: row => {
          rememberBatch(activeBatchKey(kind), row.id);
          navigate(`/admin/school/${kind}/imports/${row.id}`);
        }, onError: () => { void history.refetch(); } });
      } catch (e) { setFileError(e as Error); } finally { setReading(false); }
    }}>
      <label>上传{noun} Excel <input aria-label={`上传${noun} Excel`} type="file" accept={teacher ? ".xlsx" : ".xls,.xlsx"} disabled={busy} onChange={e => { setFile(e.target.files?.[0] || null); setFileError(null); }} /></label>
      <button className="primary-button" disabled={!file || busy}>{busy ? "正在预校验…" : "上传并预校验"}</button>
    </form>}
    {slow && <p role="status">正在等待服务器回执。可先到 <Link to={`/admin/school/${kind}/imports`}>导入记录</Link> 查看是否已完成预检，请勿重复上传。</p>}
    {upload.error && <p>如果页面没有跳转，请先查看 <Link to={`/admin/school/${kind}/imports`}>导入记录</Link>，避免重复上传。</p>}
    <ErrorDisplay error={fileError} /><ActionError action={upload} />
  </section>;
}

function RosterHistory({ kind }: { kind: Kind }) {
  const query = useJsonQuery<Row[]>(`${BASE}/roster/${kind}/imports`);
  return <QueryState query={query} empty={!query.data?.length}>
    <Table paginate headers={["文件", "状态", "上传操作人 / 时间", "操作"]}>{query.data?.map(row => <tr key={row.id}><td>{row.filename}</td><td><Badge value={row.status} /></td><td>{row.operator_name}<br />{row.created_at}</td><td><Link to={`/admin/school/${kind}/imports/${row.id}`}>查看批次</Link></td></tr>)}</Table>
  </QueryState>;
}

function RosterBatch({ id, kind }: { id: string; kind: Kind }) {
  const navigate = useNavigate();
  return <BatchDetail id={id} onClose={() => { rememberBatch(activeBatchKey(kind), ""); navigate(`/admin/school?tab=${kind}`); }} />;
}

function BatchDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const query = useJsonQuery<Row>(`${BASE}/roster/imports/${id}`);
  return <section className="panel"><div className="wb-toolbar"><h2>批次详情</h2><button onClick={onClose}>关闭批次</button></div><QueryState query={query}>{query.data && <BatchPreview key={`${id}-${query.data.status}`} batch={query.data} onRefresh={() => { void query.refetch(); }} />}</QueryState></section>;
}

function BatchPreview({ batch, onRefresh }: { batch: Row; onRefresh: () => void }) {
  const action = useAction();
  const [decisions, setDecisions] = useState<Record<number, boolean>>({});
  const [reviewed, setReviewed] = useState<Record<number, boolean>>({});
  const preview = useClientPagination<Row>(batch.rows);
  const [replacements, setReplacements] = useState<Record<number, string>>({});
  const report = batch.report, teacher = batch.kind === "teachers";
  const suspicious = report.suspicious || [];
  const ready = batch.status === "ready" && report.ok;
  const confirmed = batch.status === "succeeded";
  return <>
    <p><strong>{batch.filename}</strong> · <Badge value={batch.status} /> · 共 {report.total_rows} 行 · 错误 {report.issues.length} 行</p>
    {report.issues.length > 0 && <><p role="alert">整批未写入。请下载错误清单，全部修正后整表重新上传。</p><Download path={`/roster/imports/${batch.id}/errors`} filename="导入错误清单.xlsx">下载本批次错误清单</Download><Table paginate headers={["Excel 行号", "错误类型", "错误字段", "姓名 / 账号", "说明 / 建议"]}>{report.issues.map((issue: Row, index: number) => <tr key={index}><td>{issue.row_number ? `行${issue.row_number}` : "文件"}</td><td>{issue.error_type}</td><td>{issue.fields}</td><td>{issue.name} / {issue.account}</td><td>{issue.message}<br />{issue.suggestion}</td></tr>)}</Table></>}
    {ready && suspicious.length > 0 && <section aria-label={`疑似重复${teacher ? "教师" : "学生"}确认`}><h3>{teacher ? "疑似重复：同姓名、同年级、同科目" : "疑似重复：同姓名、同年级、同班级"}</h3><p>命中行默认保留，请逐条选择保留 / 放弃并勾选「已核对」。其余行将一并入库。</p><Table paginate headers={["Excel 行号", `待导入${teacher ? "教师" : "学生"}`, `已有${teacher ? "教师" : "学生"} / 命中范围`, "保留 / 放弃", "核对"]}>{suspicious.map((row: Row) => <tr key={row.row_number}><td>{row.row_number}</td><td>{row.name} / {row.account}</td><td>{row.matches.map((m: Row, i: number) => <p key={i}>{m.name} / {m.account} · {teacher ? m.subjects_grades.join("、") : m.grade_class}</p>)}</td><td><select aria-label={`第${row.row_number}行保留或放弃`} value={String(decisions[row.row_number] ?? true)} disabled={!canWrite()} onChange={e => setDecisions({ ...decisions, [row.row_number]: e.target.value === "true" })}><option value="true">保留（默认）</option><option value="false">放弃</option></select></td><td><label><input type="checkbox" disabled={!canWrite()} checked={!!reviewed[row.row_number]} onChange={e => setReviewed({ ...reviewed, [row.row_number]: e.target.checked })} />已核对第 {row.row_number} 行</label></td></tr>)}</Table></section>}
    {batch.rows.length > 0 && <details open={ready}><summary>原始资料预览（全部 {batch.columns.length} 列）</summary><Table headers={["Excel 行号", ...batch.columns]}>{preview.items.map((row: Row) => <tr key={row.row_number}><td>{row.row_number}</td>{batch.columns.map((field: string) => <td className="roster-value" key={field}>{row.values[field] || "—"}</td>)}</tr>)}</Table><Pager {...preview} /></details>}
    {ready && teacher && <TeacherReimports batch={batch} replacements={replacements} onChange={setReplacements} />}
    <ActionError action={action} />
    {ready && canWrite() && <><p>{teacher ? "新教师初始密码与账号一致，首次登录必须修改；变更重导沿用原密码，仍用初始密码的按新账号处理。角色和任教范围随最新资料生成。" : "确认后一次性创建学生档案和登录账号；初始密码与账号一致，首次登录修改。"}</p><button className="primary-button" disabled={action.isPending || suspicious.some((row: Row) => !reviewed[row.row_number])} onClick={() => action.mutate({ path: `/roster/imports/${batch.id}/confirm?compact=true`, body: { expected_revision: batch.revision, duplicate_decisions: Object.fromEntries(suspicious.map((row: Row) => [row.row_number, decisions[row.row_number] ?? true])), teacher_replacements: Object.fromEntries(Object.entries(replacements).filter(([number, value]) => value && decisions[Number(number)] !== false)) } }, { onSuccess: onRefresh, onError: onRefresh })}>{action.isPending ? "正在整批入库…" : "确认导入并创建账号"}</button></>}
    {confirmed && <section role="status" className="wb-status"><h3>导入完成</h3><p>成功 {report.success_count} 条 · 主动放弃 {report.skipped_count} 条</p>{teacher && <p>其中教师信息变更 {report.changed_count || 0} 条</p>}<p>操作人：{report.confirmed_by_name} · 时间：{report.confirmed_at}</p>{report.skipped_rows.length > 0 && <p>放弃的 Excel 行号：{report.skipped_rows.join("、")}</p>}{report.unresolved_teaching.length > 0 && <p>以下班级参考未匹配，教师已正常导入；可在「教师任教」维护授权：{report.unresolved_teaching.map((row: Row) => `第${row.row_number}行 ${row.references.join("、")}`).join("；")}</p>}</section>}
  </>;
}

function TeacherDeletionHistory() {
  const [search, setSearch] = useState("");
  const pagination = usePagination(search);
  const [selected, setSelected] = useState("");
  const query = useJsonQuery<PageData>(`${BASE}/roster/teachers/deletions?${new URLSearchParams({ search, page: String(pagination.page), page_size: String(pagination.pageSize) })}`);
  return <section className="panel">
    <div className="wb-toolbar"><input aria-label="删除记录姓名或账号" placeholder="教师姓名 / 原教师账号" value={search} onChange={e => setSearch(e.target.value)} /><HelpTip label="记录说明">按教师姓名或原账号查询删除快照；重新导入后仍可查阅。</HelpTip></div>
    {query.data && !query.error && <Pager {...pagination} total={query.data.total} />}
    <QueryState query={query} empty={!query.data?.items.length}><Table headers={["原教师 / 原账号", "删除人 / 时间", "重导情况", "操作"]}>{query.data?.items.map(row => <tr key={row.id}><td>{row.teacher_name}<small className="subtle">{row.account}</small></td><td>{row.operator_name}<br />{row.deleted_at}</td><td>{row.reimported_at ? `已重导 · ${row.reimported_at}` : "待重新导入"}</td><td><button onClick={() => setSelected(row.id)}>查看删除快照</button></td></tr>)}</Table></QueryState>
    {selected && <DetailDialog title="教师删除快照" onClose={() => setSelected("")}><TeacherDeletionDetail key={selected} id={selected} onClose={() => setSelected("")} /></DetailDialog>}
  </section>;
}

function TeacherDeletionDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const query = useJsonQuery<Row>(`${BASE}/roster/teachers/deletions/${id}`);
  return <section aria-label="教师删除快照"><div className="wb-toolbar"><h3>教师删除快照</h3><button onClick={onClose}>关闭快照</button></div><QueryState query={query}>{query.data && <>
    <p>{query.data.teacher_name} / {query.data.account} · 删除人：{query.data.operator_name} · {query.data.deleted_at}</p>
    <Table headers={["模板字段", "删除时的原始内容"]}>{Object.entries(query.data.fields).map(([field, value]) => <tr key={field}><td>{field}</td><td className="roster-value">{String(value || "—")}</td></tr>)}</Table>
    <h4>原教师历史任教记录</h4><Table paginate headers={["班级", "科目", "起止时间", "记录状态"]}>{query.data.teaching_history.map((row: Row) => <tr key={row.id}><td>{row.class_name}</td><td>{row.subject_name}</td><td>{row.starts_at} — {row.expires_at || "未设置截止时间"}</td><td><Badge value={row.status} /></td></tr>)}</Table>
    {!query.data.teaching_history.length && <p>暂无历史任教记录。</p>}
  </>}</QueryState></section>;
}

function TeacherReimports({ batch, replacements, onChange }: { batch: Row; replacements: Record<number, string>; onChange: (values: Record<number, string>) => void }) {
  const [search, setSearch] = useState("");
  const [labels, setLabels] = useState<Record<string, string>>({});
  const query = useJsonQuery<PageData>(`${BASE}/roster/teachers/deletions?${new URLSearchParams({ available: "true", search, page_size: "100" })}`);
  const automatic: Record<number, string> = Object.fromEntries((batch.report.reimports || []).map((row: Row) => [row.row_number, row.snapshot_id]));
  return <details open={!!batch.report.reimports?.length}><summary>教师变更重导 · 对应原教师记录</summary>
    <p>相同账号自动关联已删除的原教师；账号也变更时，请按姓名或原账号查找并指定记录。系统会沿用该教师原密码。新增教师无需选择。</p>
    <input aria-label="查找待重导教师" placeholder="搜索原教师姓名 / 原账号" maxLength={100} value={search} onChange={e => setSearch(e.target.value)} />
    <QueryState query={query}><Table paginate headers={["Excel 行号", "本次教师 / 账号", "对应的原教师"]}>{batch.rows.map((row: Row) => {
      const value = replacements[row.row_number] || automatic[row.row_number] || "";
      const choices = query.data?.items || [];
      return <tr key={row.row_number}><td>{row.row_number}</td><td>{row.values["教师姓名"]} / {row.values["教师账号"]}</td><td><select aria-label={`第${row.row_number}行原教师记录`} value={value} disabled={!canWrite()} onChange={e => {
        const chosen = choices.find(item => item.id === e.target.value);
        if (chosen) setLabels({ ...labels, [chosen.id]: `${chosen.teacher_name} / ${chosen.account}` });
        onChange({ ...replacements, [row.row_number]: e.target.value });
      }}><option value="">{automatic[row.row_number] ? "使用相同账号的原记录" : "新增教师（无需关联）"}</option>{value && !choices.some(item => item.id === value) && <option value={value}>{labels[value] || `原账号：${row.values["教师账号"]}`}</option>}{choices.map(item => <option key={item.id} value={item.id}>{item.teacher_name} / {item.account} · {item.deleted_at}</option>)}</select></td></tr>;
    })}</Table>{(query.data?.total || 0) > 100 && <p>待重导记录较多，请输入姓名或原账号缩小查找范围。</p>}</QueryState>
  </details>;
}

function LegacyAccountBinding({ id }: { id: string }) {
  const accounts = useJsonQuery<Row[]>(`${BASE}/accounts`);
  const action = useAction();
  const [saved, setSaved] = useState(false);
  if (saved) return <p role="status">已绑定账号。</p>;
  return <section><p>此前外部同步的档案可补绑现有学生账号。通过 Excel 新增的档案会自动创建账号。</p><ActionError action={action} /><QueryState query={accounts}><FormPanel title="绑定现有学生账号" fields={[{ name: "user_id", label: "账号", type: "select", options: options(accounts.data?.filter(row => row.role === "STUDENT")) }]} pending={action.isPending} onSubmit={body => action.mutate({ path: `/school/students/${id}/bind`, body }, { onSuccess: () => setSaved(true) })} /></QueryState></section>;
}
