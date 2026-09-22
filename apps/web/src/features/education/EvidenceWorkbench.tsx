import { useState } from "react";
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
  FormPanel,
  Table,
  Pager,
  useSchoolOptions,
  options,
  AssetUpload,
  AssetButton,
} from "./shared";

export function SourcesWorkbenchPage() {
  const [page, setPage] = useState(1),
    [kind, setKind] = useState(""),
    [id, setId] = useState(""),
    [file, setFile] = useState<File | null>(null),
    [error, setError] = useState<Error | null>(null),
    [reading, setReading] = useState(false);
  const list = useJsonQuery<PageData>(
      `${BASE}/sources?page=${page}${kind ? `&entity_type=${kind}` : ""}`,
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
    <AppShell title="旧资料接入与来源映射" eyebrow="业务生产 / 受控快照">
      <ReadOnlyNote />
      <p>
        当前接入方式：受控快照。这里显示导出版本、水位、内容校验和稳定映射，不表示已连接旧系统实时接口。
      </p>
      <div className="wb-toolbar">
        <select
          aria-label="来源实体"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setPage(1);
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
                <button onClick={() => setId(r.id)}>查看映射与依据</button>
              </td>
            </tr>
          ))}
        </Table>
        <Pager page={page} total={list.data?.total || 0} onChange={setPage} />
      </QueryState>
      {id && (
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
      {canWrite() && (
        <section className="panel">
          <h2>接收学校确认的导出快照</h2>
          <p>
            文件遵循受控快照契约，包含
            source_system、source_version、captured_at 和 records；学生按
            external_student_id
            匹配，原件先在试卷或报告上传区保存。整批失败不会留下部分映射。
          </p>
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
              {action.data.source_version}。请在上方列表回读。
            </p>
          )}
        </section>
      )}
    </AppShell>
  );
}

export function ReportWorkbenchPage() {
  const list = useJsonQuery<Row[]>(`${BASE}/reports`),
    students = useSchoolOptions("students"),
    exams = useSchoolOptions("exams"),
    subjects = useSchoolOptions("subjects"),
    action = useAction();
  const [asset, setAsset] = useState<Row | null>(null);
  return (
    <AppShell title="正式报告与原件" eyebrow="教学分析 / 报告版本">
      <ReadOnlyNote />
      <p>
        人工确认后的正式报告与原件按版本保存；不会自动批改或扩大学生诊断权益。学生端每次查看原件重新核验授权。
      </p>
      <QueryState query={list} empty={!list.data?.length}>
        <Table headers={["学生 / 考试", "类型 / 版本", "来源 / 时间", "原件"]}>
          {list.data?.map((r) => (
            <tr key={r.id}>
              <td>
                {students.data?.items.find((s) => s.id === r.student_id)
                  ?.name || "本校学生"}{" "}
                /{" "}
                {exams.data?.items.find((e) => e.id === r.exam_id)?.name ||
                  "历史考试"}
              </td>
              <td>
                {(
                  {
                    diagnosis: "学情诊断",
                    score_report: "成绩报告",
                    marked_work: "批阅文件",
                  } as Record<string, string>
                )[r.report_type] || r.report_type}{" "}
                · {r.version || "待补充"}
              </td>
              <td>
                {r.source_system} · {r.generated_at?.slice(0, 16)}
              </td>
              <td>
                {r.asset_id ? (
                  <AssetButton id={r.asset_id} />
                ) : (
                  <span>原件尚未接入</span>
                )}
              </td>
            </tr>
          ))}
        </Table>
      </QueryState>
      {canWrite() && (
        <section className="panel">
          <h2>保存新报告版本</h2>
          <AssetUpload label="上传正式报告原件" onUploaded={setAsset} />
          {asset && (
            <>
              <p role="status">原件已保存：{asset.filename}</p>
              <FormPanel
                key={asset.id}
                title="绑定正式报告"
                fields={[
                  {
                    name: "student_id",
                    label: "学生",
                    type: "select",
                    options: options(students.data?.items),
                  },
                  {
                    name: "exam_id",
                    label: "考试",
                    type: "select",
                    options: options(exams.data?.items),
                  },
                  {
                    name: "subject_id",
                    label: "学科（综合报告可留空）",
                    type: "select",
                    required: false,
                    options: options(subjects.data?.items),
                  },
                  {
                    name: "report_type",
                    label: "报告类型",
                    type: "select",
                    options: [
                      { value: "diagnosis", label: "学情诊断" },
                      { value: "score_report", label: "成绩报告" },
                      { value: "marked_work", label: "批阅文件" },
                    ],
                  },
                  { name: "version", label: "版本号", maxLength: 20 },
                  {
                    name: "generated_at",
                    label: "报告生成时间",
                    type: "datetime-local",
                  },
                  {
                    name: "summary",
                    label: "正式摘要",
                    type: "textarea",
                    maxLength: 10000,
                  },
                  {
                    name: "raw_content",
                    label: "报告原文（可选）",
                    type: "textarea",
                    required: false,
                    maxLength: 100000,
                  },
                ]}
                initial={{ report_type: "diagnosis" }}
                pending={action.isPending}
                onSubmit={(v) =>
                  action.mutate(
                    {
                      path: "/reports",
                      body: {
                        ...v,
                        subject_id: v.subject_id || null,
                        raw_content: v.raw_content || "",
                        generated_at: new Date(v.generated_at).toISOString(),
                        asset_id: asset.id,
                      },
                    },
                    { onSuccess: () => setAsset(null) },
                  )
                }
              />
            </>
          )}
          <ActionError action={action} />
        </section>
      )}
    </AppShell>
  );
}
