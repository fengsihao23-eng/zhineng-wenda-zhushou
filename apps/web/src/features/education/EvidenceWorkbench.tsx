import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AppShell } from "../../layouts/AppShell";
import { useJsonQuery } from "../../hooks/useApi";
import { ErrorDisplay } from "../../components/ErrorDisplay";
import {
  BASE,
  Row,
  PageData,
  QueryState,
  ReadOnlyNote,
  canWrite,
  useAction,
  ActionError,
  Table,
  Pager,
  usePagination,
  HelpTip,
} from "./shared";

export function SourcesWorkbenchPage({ view = "list" }: { view?: "list" | "create" | "detail" }) {
  const { sourceId: id = "" } = useParams();
  const [kind, setKind] = useState(""),
    [file, setFile] = useState<File | null>(null),
    [error, setError] = useState<Error | null>(null),
    [reading, setReading] = useState(false);
  const pagination = usePagination(kind);
  const { page, pageSize } = pagination;
  const list = useJsonQuery<PageData>(
      `${BASE}/sources?page=${page}&page_size=${pageSize}${kind ? `&entity_type=${kind}` : ""}`, view === "list",
    ),
    detail = useJsonQuery<Row>(`${BASE}/sources/${id}`, !!id),
    action = useAction();
  const upload = async () => {
    if (!file || reading || action.isPending) return;
    setReading(true);
    setError(null);
    try {
      if (file.size > 5_000_000) throw new Error("快照文件不能超过 5 MB。");
      const body = JSON.parse(await file.text());
      action.mutate({ path: "/legacy-snapshots", body });
    } catch (e) {
      setError(
        e instanceof SyntaxError
          ? new Error("JSON 文件格式无效。")
          : (e as Error),
      );
    } finally {
      setReading(false);
    }
  };
  return (
    <AppShell title={view === "create" ? "接入旧资料" : view === "detail" ? "来源详情" : "来源映射列表"} eyebrow="业务生产 / 旧资料与来源">
      <ReadOnlyNote />
      <div className="wb-toolbar">
        {view !== "list" && <Link className="secondary-button" to="/admin/sources">返回来源列表</Link>}
        {view === "list" && canWrite() && <Link className="primary-button" to="/admin/sources/new">接入旧资料</Link>}
        <HelpTip label="来源说明">当前通过学校确认的导出快照接入，非实时同步。可查看导出版本、时间和来源映射。</HelpTip>
      </div>
      {view === "list" && <><div className="wb-toolbar">
        <select
          aria-label="来源实体"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
          }}
        >
          <option value="">全部实体</option>
          {[
            ["exam", "旧考试"],
            ["paper", "旧试卷"],
            ["question", "旧题目"],
            ["report", "旧报告"],
            ["score", "旧成绩"],
            ["question_scores", "CSV 小题成绩"],
            ["student_exam_scores", "CSV 总分"],
          ].map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </div>
      {list.data && !list.error && <Pager {...pagination} total={list.data.total} />}
      <QueryState query={list} empty={!list.data?.items.length}>
        <Table headers={["实体 / 旧标识", "来源 / 版本", "数据水位", "操作"]}>
          {list.data?.items.map((r) => (
            <tr key={r.id}>
              <td>
                {r.entity_type} · {r.external_id}
              </td>
              <td>
                {r.source_system} / {r.source_version}
              </td>
              <td>{r.captured_at}</td>
              <td>
                <Link to={`/admin/sources/${r.id}`}>查看映射与依据</Link>
              </td>
            </tr>
          ))}
        </Table>
      </QueryState></>}
      {view === "detail" && id && (
        <section className="panel">
          <h2>来源详情</h2>
          <QueryState query={detail}>
            <dl>
              <dt>旧标识 → 新记录</dt>
              <dd className="wb-code">
                {detail.data?.external_id} → {detail.data?.native_id}
              </dd>
              <dt>内容校验</dt>
              <dd className="wb-code">{detail.data?.content_hash}</dd>
            </dl>
            <details>
              <summary>查看已受权保存的来源字段</summary>
              <pre className="wb-code">
                {JSON.stringify(detail.data?.payload, null, 2)}
              </pre>
            </details>
          </QueryState>
        </section>
      )}
      {view === "create" && canWrite() && (
        <section className="panel">
          <div className="wb-toolbar"><h2>接收学校确认的导出快照</h2><HelpTip label="文件要求">
            文件遵循受控快照契约，包含
            source_system、source_version、captured_at 和 records；学生按
            external_student_id
            匹配，原件先在试卷或报告上传区保存。整批失败不会留下部分映射。
          </HelpTip></div>
          <label>
            快照 JSON 文件
            <input
              aria-label="快照 JSON 文件"
              type="file"
              accept=".json"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </label>
          <button
            disabled={!file || reading || action.isPending}
            onClick={() => {
              void upload();
            }}
          >
            {reading
              ? "读取文件…"
              : action.isPending
                ? "核验并接入…"
                : "核验并接入快照"}
          </button>
          <ErrorDisplay error={error} />
          <ActionError action={action} />
          {action.data && (
            <p role="status" className="wb-status">
              已核验 {action.data.count} 个来源实体 · 版本{" "}
              {action.data.source_version}。<Link to="/admin/sources">查看来源列表</Link>
            </p>
          )}
        </section>
      )}
    </AppShell>
  );
}
