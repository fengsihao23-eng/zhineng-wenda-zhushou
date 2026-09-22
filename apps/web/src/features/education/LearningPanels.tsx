import { useState } from "react";
import { useJsonQuery, useApiMutation } from "../../hooks/useApi";
import { ErrorDisplay } from "../../components/ErrorDisplay";
import {
  BASE,
  Row,
  Badge,
  QueryState,
  useAction,
  ActionError,
  FormPanel,
  AssetButton,
} from "./shared";

export function MistakeStudy({ id }: { id: string }) {
  const query = useJsonQuery<Row>(`${BASE}/student/mistakes/${id}`),
    action = useAction();
  const [review, setReview] = useState("");
  return (
    <section className="panel">
      <h2>原题与复盘</h2>
      <QueryState query={query}>
        <p>
          {query.data?.score.exam} · {query.data?.score.subject} · 第{" "}
          {query.data?.score.question_no} 题 · {query.data?.score.score} /{" "}
          {query.data?.score.full_score}
        </p>
        {query.data?.question ? (
          <>
            <p>正式题目 v{query.data.question.number}</p>
            {query.data.question.parents?.map((p: Row, i: number) => (
              <section key={i}>
                <h3>{p.title}</h3>
                <p className="wb-question">{p.stem}</p>
              </section>
            ))}
            <p className="wb-question">{query.data.question.stem}</p>
            {query.data.question.options?.map((o: string, i: number) => (
              <p key={i}>{o}</p>
            ))}
            <details>
              <summary>参考答案与解析</summary>
              <p className="wb-question">
                {query.data.question.answer || "尚无参考答案"}
              </p>
              <p className="wb-question">
                {query.data.question.explanation || "尚无解析"}
              </p>
            </details>
            <button
              disabled={action.isPending}
              onClick={() =>
                action.mutate(
                  { path: "/student/reviews", body: { score_id: id } },
                  { onSuccess: (r) => setReview(r.id) },
                )
              }
            >
              加入复盘（保存记录）
            </button>
          </>
        ) : (
          <p className="inline-empty">{query.data?.missing_reason}</p>
        )}
      </QueryState>
      <ActionError action={action} />
      {review && <ReviewDetail id={review} />}
    </section>
  );
}
export function StudentReviews() {
  const query = useJsonQuery<Row[]>(`${BASE}/student/reviews`);
  const [id, setId] = useState("");
  return (
    <section className="panel">
      <h2>我的订正与复习</h2>
      <p>掌握状态由你自评记录，考试丢分不会自动推断为未掌握。</p>
      <QueryState query={query} empty={!query.data?.length}>
        {query.data?.map((r) => (
          <div className="wb-toolbar" key={r.id}>
            <span>
              {r.score.exam} · {r.score.subject} · 第 {r.score.question_no} 题
            </span>
            <Badge value={r.mastery} />
            <button onClick={() => setId(r.id)}>查看 / 记录订正</button>
          </div>
        ))}
      </QueryState>
      {id && <ReviewDetail key={id} id={id} />}
    </section>
  );
}
function ReviewDetail({ id }: { id: string }) {
  const query = useJsonQuery<Row>(`${BASE}/student/reviews/${id}`),
    action = useAction();
  const [saved, setSaved] = useState(false);
  return (
    <section>
      <h3>订正与复习记录</h3>
      <QueryState query={query}>
        <p className="wb-question">{query.data?.question?.stem}</p>
        <FormPanel
          title="保存一次复习"
          fields={[
            {
              name: "correction",
              label: "我的订正与复习笔记",
              type: "textarea",
              maxLength: 10000,
            },
            {
              name: "mastery",
              label: "自评掌握状态",
              type: "select",
              options: [
                { value: "learning", label: "仍在学习" },
                { value: "reviewing", label: "需要复习" },
                { value: "mastered", label: "自评已掌握" },
              ],
            },
            {
              name: "next_review_at",
              label: "下次复习时间",
              type: "datetime-local",
              required: false,
            },
          ]}
          initial={{ mastery: query.data?.mastery || "learning" }}
          pending={action.isPending}
          onSubmit={(v) => {
            setSaved(false);
            action.mutate(
              {
                path: `/student/reviews/${id}/records`,
                body: {
                  ...v,
                  next_review_at: v.next_review_at
                    ? new Date(v.next_review_at).toISOString()
                    : null,
                },
              },
              { onSuccess: () => setSaved(true) },
            );
          }}
        />
        {saved && (
          <p role="status" className="wb-status">
            复习记录已保存并重新读取。
          </p>
        )}
        <ActionError action={action} />
        {query.data?.records?.length ? (
          query.data.records.map((r: Row) => (
            <article className="wb-message" key={r.id}>
              <Badge value={r.mastery} />
              <small>
                {r.created_at?.slice(0, 16)} · 下次复习{" "}
                {r.next_review_at?.slice(0, 16) || "未安排"}
              </small>
              <p>{r.correction}</p>
            </article>
          ))
        ) : (
          <p>还没有订正记录。</p>
        )}
      </QueryState>
    </section>
  );
}

export function HumanConversation({
  id,
  student = false,
}: {
  id: string;
  student?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const query = useJsonQuery<Row>(`${BASE}/handoffs/${id}`, open),
    action = useAction(),
    state = useAction();
  const [content, setContent] = useState(""),
    [reason, setReason] = useState("");
  return (
    <section>
      <button
        onClick={() => {
          setOpen(!open);
          if (!open) void query.refetch();
        }}
      >
        {open ? "收起人工消息" : "查看人工消息与处理进度"}
      </button>
      {open && (
        <div className="panel">
          <QueryState query={query}>
            <div className="wb-toolbar">
              <Badge value={query.data?.status || "open"} />
              <span>处理人：{query.data?.assignee || "尚未接单"}</span>
              <button
                onClick={() => {
                  void query.refetch();
                }}
              >
                刷新消息
              </button>
            </div>
            <p>{query.data?.resolution || "暂无处理说明"}</p>
            <div role="log" aria-label="人工服务消息">
              {query.data?.messages?.length ? (
                query.data.messages.map((m: Row) => (
                  <article
                    className={`wb-message wb-message--${m.sender_role}`}
                    key={m.id}
                  >
                    <strong>
                      {m.sender_role === "staff" ? "老师" : "学生"}
                    </strong>{" "}
                    · <time>{m.created_at?.slice(0, 16)}</time>
                    <p>{m.content}</p>
                  </article>
                ))
              ) : (
                <p>暂无消息，可在工单处理中补充问题。</p>
              )}
            </div>
            <ActionError action={action} />
            <ActionError action={state} />
            {query.data?.can_reply && (
              <form
                className="wb-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (action.isPending) return;
                  action.mutate(
                    { path: `/handoffs/${id}/messages`, body: { content } },
                    { onSuccess: () => setContent("") },
                  );
                }}
              >
                <label>
                  发送人工消息
                  <textarea
                    aria-label="发送人工消息"
                    required
                    maxLength={6000}
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                  />
                </label>
                <button disabled={!content.trim() || action.isPending}>
                  发送消息
                </button>
              </form>
            )}
            {student && ["resolved", "closed"].includes(query.data?.status) && (
              <div className="wb-form">
                <label>
                  确认或重开说明
                  <textarea
                    aria-label="确认或重开说明"
                    maxLength={1000}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </label>
                <div className="wb-toolbar">
                  {[
                    "reopen",
                    ...(query.data?.status === "resolved" ? ["confirm"] : []),
                  ].map((a) => (
                    <button
                      key={a}
                      disabled={!reason.trim() || state.isPending}
                      onClick={() =>
                        state.mutate(
                          {
                            path: `/student/handoffs/${id}/${a}`,
                            body: {
                              reason,
                              expected_version: query.data?.state_version,
                            },
                          },
                          { onSuccess: () => setReason("") },
                        )
                      }
                    >
                      {a === "reopen" ? "带原因重新打开" : "确认已解决"}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <h4>处理记录</h4>
            {query.data?.history?.length ? (
              <ol>
                {query.data.history.map((h: Row, i: number) => (
                  <li key={i}>
                    {h.time?.slice(0, 16)} · <Badge value={h.status} />
                    {h.note && ` · ${h.note}`}
                  </li>
                ))}
              </ol>
            ) : (
              <p>暂无状态处理记录。</p>
            )}
          </QueryState>
        </div>
      )}
    </section>
  );
}
export function ReportVersions({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  const query = useJsonQuery<Row[]>(
    `${BASE}/student/reports/${id}/versions`,
    open,
  );
  return (
    <section>
      <button
        onClick={() => {
          setOpen(!open);
          if (!open) void query.refetch();
        }}
      >
        报告原件与版本
      </button>
      {open && (
        <QueryState query={query} empty={!query.data?.length}>
          {query.data?.map((r) => (
            <article key={r.id}>
              <p>
                版本 {r.version || "未提供"} · {r.source_system} ·{" "}
                {r.generated_at?.slice(0, 16)}
              </p>
              {r.asset_id ? (
                <AssetButton id={r.asset_id} />
              ) : (
                <p>该版本没有 PDF / 图片原件，可查看已有原文。</p>
              )}
            </article>
          ))}
        </QueryState>
      )}
    </section>
  );
}
const factLabels: Record<string, string> = {
  total_score: "总分",
  score: "得分",
  full_score: "满分",
  class_rank: "班级排名",
  grade_rank: "年级排名",
  lost_score: "丢分",
  question_no: "题号",
  exam: "考试",
  subject: "学科",
  report_version: "报告版本",
  summary: "报告摘要",
  generated_at: "生成时间",
};
export function EvidenceButton({
  messageId,
  index,
  label,
}: {
  messageId: string;
  index: number;
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const query = useJsonQuery<Row>(
    `${BASE}/evidence/${messageId}/${index}`,
    open,
  );
  const source = query.data?.captured_source;
  return (
    <div className="wb-evidence">
      <button
        onClick={() => {
          setOpen(!open);
          if (!open) void query.refetch();
        }}
      >
        {label} · 查看依据
      </button>
      {open && (
        <QueryState query={query}>
          <p>{query.data?.note}</p>
          <dl>
            {Object.entries(source?.facts || {})
              .filter(([key]) => key in factLabels)
              .map(([k, v]) => (
                <div key={k}>
                  <dt>{factLabels[k]}</dt>
                  <dd>{v == null ? "未提供" : String(v)}</dd>
                </div>
              ))}
          </dl>
          <p>
            来源：{source?.provenance?.source_system || "未记录"} · 版本：
            {source?.provenance?.source_version ||
              source?.facts?.report_version ||
              source?.as_of ||
              "原始记录"}
          </p>
          <details>
            <summary>来源校验信息</summary>
            <p className="wb-code">
              {source?.provenance?.content_hash || "此记录未接入外部来源哈希"}
            </p>
          </details>
        </QueryState>
      )}
    </div>
  );
}
export function MessageFeedback({ id }: { id: string }) {
  const action = useApiMutation<Row, { rating: string; note?: string }>(
    `/chat/messages/${id}/feedback`,
    "POST",
  );
  const [done, setDone] = useState(false);
  const readback = useJsonQuery<{feedback: {id: string; rating: string; status: string} | null}>(`/chat/messages/${id}/feedback`);
  return (
    <div>
      <div className="wb-toolbar">
        {[
          ["helpful", "有帮助"],
          ["not_helpful", "需改进"],
          ["data_wrong", "数据有误"],
          ["inappropriate", "内容不合适"],
        ].map(([rating, label]) => (
          <button
            key={rating}
            disabled={action.isPending || readback.isLoading || !!readback.error || done || !!readback.data?.feedback}
            onClick={() =>
              action.mutate({ rating }, { onSuccess: () => { setDone(true); void readback.refetch() } })
            }
          >
            {label}
          </button>
        ))}
      </div>
      {(done || readback.data?.feedback) && <small role="status">反馈已保存。</small>}
      {readback.data?.feedback && <Badge value={readback.data.feedback.status} />}
      <ErrorDisplay error={readback.error} onRetry={() => { void readback.refetch() }} />
      <ErrorDisplay error={action.error} />
    </div>
  );
}
