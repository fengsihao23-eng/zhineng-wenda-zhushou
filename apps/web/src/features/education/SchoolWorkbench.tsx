import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AppShell } from "../../layouts/AppShell";
import { getUserInfo } from "../../utils/auth";
import { RosterWorkbench } from "./RosterWorkbench";
import { ExamWorkbench } from "./ExamWorkbench";
import { useJsonQuery } from "../../hooks/useApi";
import {
  BASE,
  type Row,
  QueryState,
  ReadOnlyNote,
  canWrite,
  Table,
  HelpTip,
  useSchoolOptions,
} from "./shared";

const tabs: Record<string, string> = {
  students: "学生档案",
  teachers: "教师档案",
  "exam-management": "考务管理",
};

function savedSchoolTab(key: string): string | null {
  try { return sessionStorage.getItem(key); } catch { return null; }
}

function saveSchoolTab(key: string, tab: string): void {
  try { sessionStorage.setItem(key, tab); } catch { return; }
}

export function SchoolWorkbenchPage() {
  const user = getUserInfo();
  const examAdmin = (user?.roles || []).includes("EXAM_ADMIN");
  const examOnly = examAdmin && !canWrite();
  const [params, setParams] = useSearchParams();
  const tabKey = `school-workbench-tab:${user?.school_id || "unknown"}:${user?.user_id || "anonymous"}`;
  const requestedTab = params.get("tab");
  const lastTab = savedSchoolTab(tabKey);
  const availableTabs = examOnly ? ["exam-management"] : Object.keys(tabs);
  const kind = requestedTab && availableTabs.includes(requestedTab) ? requestedTab
    : lastTab && availableTabs.includes(lastTab) ? lastTab : "exam-management";
  useEffect(() => {
    if (!examOnly) saveSchoolTab(tabKey, kind);
    if (requestedTab !== kind) setParams({ tab: kind }, { replace: true });
  }, [examOnly, kind, requestedTab, setParams, tabKey]);
  const writable = canWrite() || (examAdmin && kind === "exam-management");
  return (
    <AppShell title="师生班级与考试" eyebrow="业务生产 / 学校范围">
      {!examOnly && <ReadOnlyNote />}
      <div className="wb-tabs">
        {availableTabs.map(key => (
          <button key={key} className={kind === key ? "active" : ""}
            onClick={() => setParams({ tab: key })}>{tabs[key]}</button>
        ))}
      </div>
      {kind === "exam-management" ? <ExamWorkbench writable={writable} />
        : <RosterWorkbench key={kind} kind={kind as "teachers" | "students"} />}
    </AppShell>
  );
}
export function ClassAnalysisPage() {
  const classes = useSchoolOptions("classes"),
    subjects = useSchoolOptions("subjects"),
    exams = useSchoolOptions("exams");
  const [scope, setScope] = useState({
    class_id: "",
    subject_id: "",
    exam_id: "",
  });
  const ready = Object.values(scope).every(Boolean);
  const query = useJsonQuery<Row>(
    `${BASE}/class-analysis?${new URLSearchParams(scope)}`,
    ready,
  );
  const teacher = getRole() === "teacher";
  return (
    <AppShell title="班级学科分析" eyebrow="教学分析 / 授权任教范围">
      <div className="wb-toolbar">
        {[
          ["class_id", "班级", classes],
          ["subject_id", "学科", subjects],
          ["exam_id", "考试", exams],
        ].map(([key, label, q]) => (
          <label key={String(key)}>
            {String(label)}
            <select
              aria-label={String(label)}
              value={scope[key as keyof typeof scope]}
              onChange={(e) =>
                setScope({ ...scope, [String(key)]: e.target.value })
              }
            >
              <option value="">请选择</option>
              {(q as typeof classes).data?.items.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      {[classes, subjects, exams]
        .filter((q) => q.error)
        .map((q, i) => (
          <QueryState key={i} query={q}>
            {null}
          </QueryState>
        ))}
      {!ready ? (
        <p className="inline-empty">
          选择班级、学科和考试后读取汇总。无任教关系时不会展示全校数据。
        </p>
      ) : (
        <QueryState query={query}>
          <p>
            样本量：{query.data?.sample_size ?? 0} · 平均分：
            {query.data?.average ?? "暂无"} · 最低 / 最高：
            {query.data?.minimum ?? "—"} / {query.data?.maximum ?? "—"}
          </p>
          {query.data?.note && <HelpTip label="统计说明">{query.data.note}</HelpTip>}
          <h2>得分率分布</h2>
          <div className="wb-toolbar">
            {query.data?.distribution?.map((bucket: Row) => (
              <span key={bucket.label}>
                {bucket.label}：{bucket.count} 人
              </span>
            ))}
          </div>
          {query.data?.previous_exam ? (
            <p>
              上次 {query.data.previous_exam.exam} · 样本{" "}
              {query.data.previous_exam.sample_size} 人 · 平均分{" "}
              {query.data.previous_exam.average} · 同满分平均变化{" "}
              {query.data.previous_exam.average_delta ?? "不可比较"}
              （两次样本可能不同）
            </p>
          ) : (
            <p>暂无可比较的上次考试。</p>
          )}
          <h2>知识点丢分事实</h2>
          {!query.data?.knowledge_points?.length && (
            <p>
              暂无知识点统计。未映射小题数：
              {query.data?.unmapped_question_count ?? 0}
            </p>
          )}
          <Table key={`knowledge-${JSON.stringify(scope)}`} paginate headers={["知识点", "累计丢分", "小题记录", "学生样本量"]}>
            {query.data?.knowledge_points?.map((p: Row) => (
              <tr key={p.name}>
                <td>{p.name}</td>
                <td>{p.lost_score}</td>
                <td>{p.question_count}</td>
                <td>{p.sample_size}</td>
              </tr>
            ))}
          </Table>
          <h2>学生详情下钻</h2>
          <Table key={`students-${JSON.stringify(scope)}`} paginate headers={["匿名序号", "得分", "操作"]}>
            {query.data?.students?.map((s: Row) => (
              <tr key={s.student_id}>
                <td>{s.label}</td>
                <td>
                  {s.score} / {s.full_score}
                </td>
                <td>
                  <Link
                    to={`/${teacher ? "teacher" : "admin"}/students/${s.student_id}`}
                  >
                    查看学情
                  </Link>
                </td>
              </tr>
            ))}
          </Table>
        </QueryState>
      )}
    </AppShell>
  );
}
import { roleOf } from "../../layouts/AppShell";
const getRole = () => roleOf(getUserInfo());
