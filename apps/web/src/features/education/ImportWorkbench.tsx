import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../layouts/AppShell";
import { useJsonQuery } from "../../hooks/useApi";
import { ErrorDisplay } from "../../components/ErrorDisplay";
import {
  BASE,
  type Row,
  Badge,
  QueryState,
  useAction,
  ActionError,
  Table,
  canWrite,
  ReadOnlyNote,
} from "./shared";

export function ImportWorkbenchPage() {
  const list = useJsonQuery<Row[]>(`${BASE}/imports`);
  const upload = useAction();
  const [id, setId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [batch, setBatch] = useState("");
  const [source, setSource] = useState("school_csv");
  const [error, setError] = useState<Error | null>(null);
  const [reading, setReading] = useState(false);
  const send = async () => {
    if (reading || upload.isPending) return;
    setReading(true);
    setError(null);
    try {
      if (files.reduce((n, f) => n + f.size, 0) > 5_000_000)
        throw new Error("总文件大小不能超过 5 MB。");
      const payload: Record<string, string> = {};
      for (const file of files) {
        if (payload[file.name]) throw new Error("文件名重复。");
        payload[file.name] = await file.text();
      }
      upload.mutate(
        {
          path: "/imports",
          body: { batch_key: batch, source_system: source, files: payload },
        },
        { onSuccess: (r) => setId(r.id) },
      );
    } catch (e) {
      setError(e as Error);
    } finally {
      setReading(false);
    }
  };
  return (
    <AppShell title="成绩导入工作台" eyebrow="业务生产 / 导入与回执">
      <ReadOnlyNote />
      <p>
        上传八类 CSV → 字段映射 → 预检逐行错误 → 确认事务导入 →
        进度与回执。档案导入后还需单独绑定登录账号。
      </p>
      <p className="wb-help">
        支持 UTF-8
        CSV：schools、classes、students、exams、subjects、student_exam_scores、student_subject_scores、question_scores。每个文件名须带
        .csv。
      </p>
      {canWrite() && (
        <form
          className="panel wb-form"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <label className="form-field">
            批次编号
            <input
              aria-label="批次编号"
              pattern="[a-zA-Z0-9_-]+"
              maxLength={80}
              value={batch}
              onChange={(e) => setBatch(e.target.value)}
              required
            />
          </label>
          <label className="form-field">
            来源系统
            <input
              aria-label="来源系统"
              pattern="[a-zA-Z0-9_-]+"
              maxLength={50}
              value={source}
              onChange={(e) => setSource(e.target.value)}
              required
            />
          </label>
          <label>
            选择 CSV 文件
            <input
              aria-label="选择 CSV 文件"
              type="file"
              accept=".csv"
              multiple
              required
              onChange={(e) => setFiles(Array.from(e.target.files || []))}
            />
          </label>
          <button
            className="primary-button"
            disabled={reading || upload.isPending || !files.length}
          >
            {reading
              ? "读取文件…"
              : upload.isPending
                ? "上传保存…"
                : "上传新批次"}
          </button>
        </form>
      )}
      <ErrorDisplay error={error} />
      <ActionError action={upload} />
      <QueryState query={list} empty={!list.data?.length}>
        <Table headers={["批次", "来源", "状态", "操作"]}>
          {list.data?.map((row) => (
            <tr key={row.id}>
              <td>{row.batch_key}</td>
              <td>{row.source_system}</td>
              <td>
                <Badge value={row.status} />
              </td>
              <td>
                <button onClick={() => setId(row.id)}>映射 / 查看回执</button>
              </td>
            </tr>
          ))}
        </Table>
      </QueryState>
      {id && <ImportDetail key={id} id={id} />}
    </AppShell>
  );
}
function ImportDetail({ id }: { id: string }) {
  const query = useJsonQuery<Row>(`${BASE}/imports/${id}`);
  const templates = useJsonQuery<Row[]>(`${BASE}/mapping-templates`);
  const action = useAction();
  const saveTemplate = useAction();
  const confirm = useAction();
  const [mapping, setMapping] = useState<
    Record<string, Record<string, string>>
  >({});
  const [dirty, setDirty] = useState(false);
  const [ack, setAck] = useState(false);
  const [templateName, setTemplateName] = useState("");
  useEffect(() => {
    if (query.data && !dirty) setMapping(query.data.mapping || {});
  }, [query.data, dirty]);
  useEffect(() => {
    if (query.data?.status !== "running") return;
    const timer = setInterval(() => {
      void query.refetch();
    }, 1500);
    return () => clearInterval(timer);
  }, [query.data?.status, query.refetch]);
  const frozen = ["running", "succeeded"].includes(query.data?.status);
  const preflight = () =>
    action.mutate(
      {
        path: `/imports/${id}/preflight`,
        body: { expected_revision: query.data?.revision, mapping },
      },
      {
        onSuccess: () => {
          setDirty(false);
          setAck(false);
        },
      },
    );
  return (
    <section className="panel">
      <h2>批次详情</h2>
      <QueryState query={query}>
        <div className="wb-toolbar">
          <Badge value={query.data?.status || "uploaded"} />
          <button
            onClick={() => {
              void query.refetch();
            }}
          >
            重新读取
          </button>
          <span>映射版本 {query.data?.revision}</span>
        </div>
        <ActionError action={action} />
        <ActionError action={confirm} />
        <ActionError action={saveTemplate} />
        <div className="wb-toolbar">
          <label>
            映射模板
            <select
              aria-label="映射模板"
              disabled={frozen || !canWrite()}
              onChange={(e) => {
                const t = templates.data?.find((t) => t.id === e.target.value);
                if (t) {
                  setMapping(t.mapping);
                  setDirty(true);
                  setAck(false);
                }
              }}
            >
              <option value="">使用已有模板</option>
              {templates.data?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} v{t.version}
                </option>
              ))}
            </select>
          </label>
        </div>
        {Object.entries(query.data?.files || {}).map(([file, value]) => {
          const meta = value as { headers: string[]; row_count: number };
          const schema = query.data?.schema[file];
          return (
            <details key={file} open>
              <summary>
                {file} · {meta.row_count} 行
              </summary>
              <div className="wb-mapping">
                {Array.from(
                  new Set<string>([
                    ...(schema?.required || []),
                    ...(schema?.optional || []),
                  ]),
                ).map((field) => (
                  <label key={field}>
                    {field}
                    {schema?.required.includes(field) ? " *" : ""}
                    <select
                      aria-label={`${file} ${field}`}
                      disabled={frozen || !canWrite()}
                      value={mapping[file]?.[field] || ""}
                      onChange={(e) => {
                        const next = { ...(mapping[file] || {}) };
                        if (e.target.value) next[field] = e.target.value;
                        else delete next[field];
                        setMapping({ ...mapping, [file]: next });
                        setDirty(true);
                        setAck(false);
                      }}
                    >
                      <option value="">不映射</option>
                      {meta.headers.map((h) => (
                        <option key={h}>{h}</option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            </details>
          );
        })}
        {canWrite() && !frozen && (
          <div className="wb-toolbar">
            <button disabled={action.isPending} onClick={preflight}>
              {action.isPending ? "预检中…" : "保存映射并预检"}
            </button>
            <input
              aria-label="模板名称"
              placeholder="模板名称"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
            />
            <button
              disabled={!templateName.trim() || saveTemplate.isPending}
              onClick={() =>
                saveTemplate.mutate({
                  path: "/mapping-templates",
                  body: { name: templateName, mapping },
                })
              }
            >
              保存为新模板版本
            </button>
          </div>
        )}
        {query.data?.report?.issues?.length > 0 && (
          <div className="wb-error-list" role="alert">
            <h3>逐行错误（修正原 CSV 后使用新批次）</h3>
            <Table headers={["文件", "行", "错误码 / 字段说明"]}>
              {query.data?.report.issues.map((i: Row, n: number) => (
                <tr key={n}>
                  <td>{i.file}</td>
                  <td>{i.row ?? "整文件"}</td>
                  <td>
                    {i.code} · {i.message}
                  </td>
                </tr>
              ))}
            </Table>
          </div>
        )}
        {query.data?.status === "ready" && canWrite() && (
          <section>
            <p>
              预检通过，共 {query.data.report.total_rows}{" "}
              行。确认后会一次性写入；失败会整批回滚。
            </p>
            <label>
              <input
                type="checkbox"
                checked={ack}
                disabled={dirty}
                onChange={(e) => setAck(e.target.checked)}
              />
              已核对当前学校、映射和批次范围
            </label>
            <button
              className="primary-button"
              disabled={!ack || dirty || confirm.isPending}
              onClick={() =>
                confirm.mutate(
                  {
                    path: `/imports/${id}/confirm`,
                    body: { expected_revision: query.data?.revision },
                  },
                  {
                    onSuccess: () => {
                      setAck(false);
                      void query.refetch();
                    },
                  },
                )
              }
            >
              确认导入
            </button>
            {dirty && <p>映射有未预检修改，请先重新预检。</p>}
          </section>
        )}
        {query.data?.status === "running" && (
          <p role="status">
            事务处理中；整批提交前不会显示为成功。
            <progress className="wb-progress" aria-label="导入进度" />
          </p>
        )}
        {query.data?.status === "failed" && (
          <div role="alert">
            <p>
              {query.data.report.message || "预检或写入失败，业务数据未提交。"}
            </p>
            <button
              disabled={confirm.isPending || !canWrite()}
              onClick={() =>
                confirm.mutate({
                  path: `/imports/${id}/confirm`,
                  body: { expected_revision: query.data?.revision },
                })
              }
            >
              重试原批次
            </button>
          </div>
        )}
        {query.data?.status === "succeeded" && (
          <div className="wb-status" role="status">
            <h3>导入回执</h3>
            <p>
              已提交 {query.data.report.imported_rows} 行 · 未绑定账号{" "}
              {query.data.report.unbound_accounts} 个
            </p>
            <p className="wb-code">
              内容校验：{query.data.report.batch_content_hash}
            </p>
            <ul>
              {Object.entries(query.data.report.counts || {}).map(([k, v]) => (
                <li key={k}>
                  {k}：{String(v)}
                </li>
              ))}
            </ul>
            <Link to="/admin/school">进入学生账号绑定</Link> ·{" "}
            <Link to="/admin/sources">查看来源映射</Link>
          </div>
        )}
      </QueryState>
    </section>
  );
}
