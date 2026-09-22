import { useState } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../layouts/AppShell";
import { useJsonQuery } from "../../hooks/useApi";
import {
  BASE,
  type Row,
  type PageData,
  type Field,
  Badge,
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
} from "./shared";

const tabs: Record<string, string> = {
  classes: "班级",
  students: "学生与账号",
  teachers: "教师账号",
  teaching: "教师任教",
  subjects: "学科",
  exams: "考试科目",
};
export function SchoolWorkbenchPage() {
  const [kind, setKind] = useState("classes");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Row | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const list = useJsonQuery<PageData>(
    `${BASE}/school/${kind}?page=${page}&search=${encodeURIComponent(search)}`,
  );
  const classes = useSchoolOptions("classes"),
    subjects = useSchoolOptions("subjects");
  const accounts = useJsonQuery<Row[]>(`${BASE}/accounts`);
  const create = useAction();
  const update = useAction("PUT");
  const bind = useAction();
  const [notice, setNotice] = useState("");
  const statusField: Field = {
    name: "status",
    label: "状态",
    type: "select",
    options: [
      { value: "active", label: "有效" },
      { value: "inactive", label: "停用（保留历史）" },
    ],
  };
  const fields: Record<string, Field[]> = {
    teachers: [{ name: "display_name", label: "教师显示名称" }, statusField],
    classes: [
      { name: "external_class_id", label: "外部班级标识" },
      { name: "name", label: "班级名称" },
    ],
    students: [
      { name: "external_student_id", label: "外部学生标识" },
      { name: "student_no", label: "学号" },
      { name: "name", label: "姓名" },
      {
        name: "class_id",
        label: "班级",
        type: "select",
        options: options(classes.data?.items),
      },
    ],
    subjects: [
      { name: "external_subject_id", label: "外部学科标识" },
      { name: "code", label: "学科代码" },
      { name: "name", label: "学科名称" },
    ],
    exams: [
      { name: "external_exam_id", label: "外部考试标识" },
      { name: "name", label: "考试名称" },
      { name: "exam_type", label: "考试类型" },
      { name: "start_date", label: "开始日期", type: "date" },
      { name: "end_date", label: "结束日期", type: "date", required: false },
      statusField,
    ],
    teaching: [
      {
        name: "teacher_user_id",
        label: "教师账号",
        type: "select",
        options: options(accounts.data?.filter((a) => a.role === "TEACHER")),
      },
      {
        name: "class_id",
        label: "班级",
        type: "select",
        options: options(classes.data?.items),
      },
      {
        name: "subject_id",
        label: "学科",
        type: "select",
        options: options(subjects.data?.items),
      },
      { name: "starts_at", label: "生效时间", type: "datetime-local" },
      {
        name: "expires_at",
        label: "到期时间",
        type: "datetime-local",
        required: false,
      },
      statusField,
    ],
  };
  const normalize = (v: Record<string, any>) => ({
    ...v,
    ...(kind === "exams"
      ? { end_date: v.end_date || null, status: v.status || "active" }
      : {}),
    ...(kind === "teaching"
      ? {
          starts_at: new Date(v.starts_at).toISOString(),
          expires_at: v.expires_at
            ? new Date(v.expires_at).toISOString()
            : null,
        }
      : {}),
  });
  const saved = () => {
    setSelected(null);
    setShowCreate(false);
    setNotice("已保存。列表已从服务端重新读取。");
  };
  const editFields =
    kind === "classes"
      ? [{ name: "name", label: "班级名称" } as Field, statusField]
      : kind === "students"
        ? [fields.students[3], statusField]
        : fields[kind];
  return (
    <AppShell title="师生班级与考试" eyebrow="业务生产 / 学校范围">
      <ReadOnlyNote />
      <p className="wb-help">
        身份按外部标识绑定；导入档案与登录账号分别管理。停用不删除历史成绩，外部来源记录保留只读。
      </p>
      <div className="wb-tabs">
        {Object.entries(tabs).map(([key, label]) => (
          <button
            key={key}
            className={kind === key ? "active" : ""}
            onClick={() => {
              setKind(key);
              setPage(1);
              setSelected(null);
              setShowCreate(false);
              setNotice("");
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="wb-toolbar">
        <input
          aria-label="搜索名称"
          placeholder="搜索名称"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
        {canWrite() && kind !== "teachers" && (
          <button
            onClick={() => {
              setShowCreate(!showCreate);
              setSelected(null);
            }}
          >
            新建{tabs[kind]}
          </button>
        )}
      </div>
      {kind === "teachers" && (
        <p>
          维护已有教师账号的显示名称和状态；账号开通沿用当前身份流程，任教授权在“教师任教”中单独维护。
        </p>
      )}
      <ActionError action={create} />
      <ActionError action={update} />
      <ActionError action={bind} />
      {notice && (
        <p role="status" className="wb-status">
          {notice}
        </p>
      )}
      {accounts.error && <QueryState query={accounts}>{null}</QueryState>}
      {showCreate && (
        <FormPanel
          key={kind}
          title={`新建${tabs[kind]}`}
          fields={fields[kind]}
          initial={{ status: "active" }}
          pending={create.isPending}
          onSubmit={(values) =>
            create.mutate(
              { path: `/school/${kind}`, body: normalize(values) },
              { onSuccess: saved },
            )
          }
        />
      )}
      <QueryState query={list} empty={!list.data?.items.length}>
        <Table
          headers={
            kind === "teaching"
              ? ["教师", "班级 / 学科", "生效与到期", "状态", "操作"]
              : ["名称 / 标识", "来源", "状态 / 绑定", "操作"]
          }
        >
          {list.data?.items.map((row) => (
            <tr key={row.id}>
              {kind === "teaching" ? (
                <>
                  <td>
                    {accounts.data?.find((a) => a.id === row.teacher_user_id)
                      ?.name || "未读取账号"}
                  </td>
                  <td>
                    {classes.data?.items.find((c) => c.id === row.class_id)
                      ?.name || "当前页外班级"}{" "}
                    /{" "}
                    {subjects.data?.items.find((s) => s.id === row.subject_id)
                      ?.name || "学科"}
                  </td>
                  <td>
                    {row.starts_at?.slice(0, 16)}
                    <br />
                    {row.expires_at?.slice(0, 16) || "无到期时间"}
                  </td>
                  <td>
                    <Badge value={row.status} />
                  </td>
                </>
              ) : (
                <>
                  <td>
                    <strong>{row.name}</strong>
                    <small className="subtle">
                      {row.external_student_id ||
                        row.external_class_id ||
                        row.external_exam_id ||
                        row.external_subject_id}
                    </small>
                  </td>
                  <td>
                    {kind === "teachers"
                      ? "现有身份账号"
                      : row.source_system || "待补充"}
                  </td>
                  <td>
                    {row.status && <Badge value={row.status} />}{" "}
                    {kind === "students" &&
                      (row.user_id ? "已绑定账号" : "待绑定账号")}
                  </td>
                </>
              )}
              <td>
                {canWrite() &&
                  (["teaching", "teachers"].includes(kind) ||
                    row.source_system === "native") &&
                  kind !== "subjects" && (
                    <button
                      onClick={() => {
                        setSelected(row);
                        setShowCreate(false);
                      }}
                    >
                      维护
                    </button>
                  )}
                {kind === "students" && canWrite() && (
                  <button onClick={() => setSelected(row)}>账号绑定</button>
                )}
                {kind === "exams" && (
                  <button onClick={() => setSelected(row)}>考试科目</button>
                )}
                {kind === "students" && (
                  <Link to={`/admin/students/${row.id}`}>查看学情</Link>
                )}
              </td>
            </tr>
          ))}
        </Table>
        <Pager page={page} total={list.data?.total || 0} onChange={setPage} />
      </QueryState>
      {selected && (
        <section className="panel">
          <div className="wb-toolbar">
            <h2>{selected.name || "任教关系"}</h2>
            <button onClick={() => setSelected(null)}>关闭详情</button>
          </div>
          {canWrite() &&
            (["teaching", "teachers"].includes(kind) ||
              selected.source_system === "native") && (
              <FormPanel
                key={`${kind}-${selected.id}`}
                title="维护当前记录"
                fields={editFields}
                initial={Object.fromEntries(
                  editFields.map((f) => [
                    f.name,
                    f.type === "datetime-local"
                      ? selected[f.name]?.slice(0, 16)
                      : selected[f.name],
                  ]),
                )}
                pending={update.isPending}
                onSubmit={(v) =>
                  update.mutate(
                    {
                      path: `/school/${kind}/${selected.id}`,
                      body: normalize(v),
                    },
                    { onSuccess: saved },
                  )
                }
              />
            )}
          {kind === "students" && canWrite() && (
            <FormPanel
              key={`bind-${selected.id}`}
              title="绑定现有学生账号"
              fields={[
                {
                  name: "user_id",
                  label: "账号",
                  type: "select",
                  options: options(
                    accounts.data?.filter((a) => a.role === "STUDENT"),
                  ),
                },
              ]}
              pending={bind.isPending}
              onSubmit={(v) =>
                bind.mutate(
                  { path: `/school/students/${selected.id}/bind`, body: v },
                  { onSuccess: saved },
                )
              }
            />
          )}
          {kind === "exams" && (
            <ExamSubjects
              id={selected.id}
              writable={selected.source_system === "native" && canWrite()}
            />
          )}
        </section>
      )}
    </AppShell>
  );
}
function ExamSubjects({ id, writable }: { id: string; writable: boolean }) {
  const detail = useJsonQuery<Row>(`${BASE}/exams/${id}`),
    subjects = useSchoolOptions("subjects"),
    action = useAction("PUT");
  return (
    <>
      <QueryState query={detail}>
        <h3>已配置科目</h3>
        {detail.data?.subjects?.length ? (
          <ul>
            {detail.data.subjects.map((s: Row) => (
              <li key={s.subject_id}>
                {s.name} · 满分 {s.full_score}
              </li>
            ))}
          </ul>
        ) : (
          <p>尚未配置科目。</p>
        )}
      </QueryState>
      <ActionError action={action} />
      {writable && (
        <FormPanel
          title="配置科目与满分"
          fields={[
            {
              name: "subject_id",
              label: "学科",
              type: "select",
              options: options(subjects.data?.items),
            },
            {
              name: "full_score",
              label: "满分",
              type: "number",
              min: 0.01,
              max: 10000,
              step: "0.01",
            },
          ]}
          pending={action.isPending}
          onSubmit={(body) =>
            action.mutate({ path: `/exams/${id}/subjects`, body })
          }
        />
      )}
    </>
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
          <p className="wb-help">{query.data?.note}</p>
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
          <Table headers={["知识点", "累计丢分", "小题记录", "学生样本量"]}>
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
          <Table headers={["匿名序号", "得分", "操作"]}>
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
                    查看授权学情（记录访问）
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
import { getUserInfo } from "../../utils/auth";
const getRole = () => roleOf(getUserInfo());
