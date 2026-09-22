import { useState } from "react";
import { AppShell } from "../../layouts/AppShell";
import { useJsonQuery } from "../../hooks/useApi";
import {
  BASE,
  Row,
  PageData,
  Field,
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
  labels,
} from "./shared";

export function QuestionWorkbenchPage() {
  const [tab, setTab] = useState<"questions" | "taxonomy">("questions");
  return (
    <AppShell title="题库与知识点" eyebrow="业务生产 / 单一题库">
      <ReadOnlyNote />
      <div className="wb-tabs">
        <button
          className={tab === "questions" ? "active" : ""}
          onClick={() => setTab("questions")}
        >
          题目与材料
        </button>
        <button
          className={tab === "taxonomy" ? "active" : ""}
          onClick={() => setTab("taxonomy")}
        >
          知识点树与标签
        </button>
      </div>
      {tab === "questions" ? <Questions /> : <Taxonomy />}
    </AppShell>
  );
}
function Questions() {
  const subjects = useSchoolOptions("subjects");
  const [subject, setSubject] = useState("");
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");
  const [deleted, setDeleted] = useState(false);
  const [page, setPage] = useState(1);
  const [id, setId] = useState("");
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const list = useJsonQuery<PageData>(
    `${BASE}/questions?${new URLSearchParams({ page: String(page), search, deleted: String(deleted), ...(subject ? { subject_id: subject } : {}), ...(kind ? { kind } : {}) })}`,
  );
  const action = useAction<{ items: Row[] }>();
  const [receipt, setReceipt] = useState<Row[]>([]);
  return (
    <>
      <div className="wb-toolbar">
        <label>
          学科
          <select
            aria-label="题库学科"
            value={subject}
            onChange={(e) => {
              setSubject(e.target.value);
              setPage(1);
            }}
          >
            <option value="">全部学科</option>
            {subjects.data?.items.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          题目层级
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setPage(1);
            }}
          >
            <option value="">全部层级</option>
            {["material", "major", "minor", "standalone"].map((k) => (
              <option key={k} value={k}>
                {labels[k]}
              </option>
            ))}
          </select>
        </label>
        <input
          aria-label="题目搜索"
          placeholder="搜索题目名称"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
        <label>
          <input
            type="checkbox"
            checked={deleted}
            onChange={(e) => {
              setDeleted(e.target.checked);
              setSelected([]);
              setPage(1);
            }}
          />
          回收站
        </label>
        {canWrite() && (
          <button onClick={() => setCreating(!creating)}>新建题目</button>
        )}
      </div>
      <ActionError action={action} />
      {creating && (
        <QuestionForm
          onSaved={(row) => {
            setId(row.id);
            setCreating(false);
          }}
          parents={list.data?.items || []}
        />
      )}
      <QueryState query={list} empty={!list.data?.items.length}>
        <Table headers={["选择", "标题 / 层级", "状态 / 来源", "操作"]}>
          {list.data?.items.map((row) => (
            <tr key={row.id}>
              <td>
                <input
                  aria-label={`选择 ${row.title}`}
                  type="checkbox"
                  disabled={!canWrite() || row.source_system !== "native"}
                  checked={selected.includes(row.id)}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? [...selected, row.id]
                        : selected.filter((i) => i !== row.id),
                    )
                  }
                />
              </td>
              <td>
                <strong>{row.title}</strong>
                <div>
                  <Badge value={row.kind} />
                  {row.parent_id && (
                    <button onClick={() => setId(row.parent_id)}>
                      查看父级
                    </button>
                  )}
                </div>
              </td>
              <td>
                <Badge value={row.status} /> · {row.source_system}
              </td>
              <td>
                <button onClick={() => setId(row.id)}>
                  正文 / 版本 / 解析
                </button>
              </td>
            </tr>
          ))}
        </Table>
        <Pager page={page} total={list.data?.total || 0} onChange={setPage} />
      </QueryState>
      {canWrite() && selected.length > 0 && (
        <div className="wb-toolbar">
          <span>已选择 {selected.length} 条，操作前自动检查引用。</span>
          <button
            disabled={action.isPending}
            onClick={() =>
              action.mutate(
                {
                  path: "/questions/batch",
                  body: {
                    ids: selected,
                    action: deleted ? "restore" : "delete",
                  },
                },
                {
                  onSuccess: (r) => {
                    setReceipt(r.items);
                    setSelected([]);
                  },
                },
              )
            }
          >
            {deleted ? "恢复所选" : "软删除所选"}
          </button>
        </div>
      )}
      {!!receipt.length && (
        <section className="panel" role="status">
          <h3>逐项操作回执</h3>
          <ul>
            {receipt.map((r) => (
              <li key={r.id}>
                {r.id.slice(0, 8)}：{r.ok ? "已完成" : r.message}
                {r.references &&
                  `（${Object.entries(r.references)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join("，")}）`}
              </li>
            ))}
          </ul>
        </section>
      )}
      {id && (
        <QuestionDetail
          key={id}
          id={id}
          onClose={() => setId("")}
          onSelect={setId}
        />
      )}
    </>
  );
}
const bodyFields: Field[] = [
  { name: "stem", label: "题干 / 材料正文", type: "textarea" },
  {
    name: "options_text",
    label: "选项（每行一个）",
    type: "textarea",
    required: false,
  },
  { name: "answer", label: "参考答案", type: "textarea", required: false },
  { name: "explanation", label: "解析", type: "textarea", required: false },
];
function QuestionForm({
  parents,
  onSaved,
  item,
  version,
}: {
  parents: Row[];
  onSaved: (row: Row) => void;
  item?: Row;
  version?: Row;
}) {
  const subjects = useSchoolOptions("subjects"),
    tags = useJsonQuery<Row[]>(`${BASE}/taxonomy`),
    action = useAction();
  const [tagIds, setTagIds] = useState<string[]>(
    version?.tags?.map((t: Row) => t.id) || [],
  );
  const fields: Field[] = item
    ? bodyFields
    : [
        { name: "title", label: "题目名称" },
        {
          name: "subject_id",
          label: "学科",
          type: "select",
          options: options(subjects.data?.items),
        },
        {
          name: "kind",
          label: "层级",
          type: "select",
          options: ["material", "major", "minor", "standalone"].map((k) => ({
            value: k,
            label: labels[k],
          })),
        },
        {
          name: "parent_id",
          label: "父级材料 / 大题",
          type: "select",
          required: false,
          options: options(
            parents.filter((p) => ["material", "major"].includes(p.kind)),
            "title",
          ),
        },
        ...bodyFields,
      ];
  const submit = (v: Record<string, any>) => {
    const { options_text, ...rest } = v;
    const body = {
      ...rest,
      options: (options_text || "")
        .split("\n")
        .map((s: string) => s.trim())
        .filter(Boolean),
      answer: v.answer || "",
      explanation: v.explanation || "",
      tag_ids: tagIds,
      ...(item
        ? {
            expected_revision: item.revision,
            paper_version_id: version?.paper_version_id || null,
            regions: version?.regions || [],
          }
        : { parent_id: v.parent_id || null }),
    };
    action.mutate(
      { path: item ? `/questions/${item.id}/versions` : "/questions", body },
      { onSuccess: onSaved },
    );
  };
  return (
    <>
      <ActionError action={action} />
      <FormPanel
        title={item ? "保存新题目版本" : "新建题目草稿"}
        fields={fields}
        initial={
          version
            ? {
                stem: version.stem,
                options_text: version.options?.join("\n"),
                answer: version.answer,
                explanation: version.explanation,
              }
            : { kind: "standalone" }
        }
        pending={action.isPending}
        onSubmit={submit}
      >
        <fieldset>
          <legend>知识点与标签（只能选择同学科）</legend>
          <QueryState query={tags} empty={!tags.data?.length}>
            {tags.data?.map((t) => (
              <label key={t.id}>
                <input
                  type="checkbox"
                  checked={tagIds.includes(t.id)}
                  onChange={(e) =>
                    setTagIds(
                      e.target.checked
                        ? [...tagIds, t.id]
                        : tagIds.filter((id) => id !== t.id),
                    )
                  }
                />
                {t.name} · {labels[t.kind]}
              </label>
            ))}
          </QueryState>
        </fieldset>
      </FormPanel>
    </>
  );
}
function QuestionDetail({
  id,
  onClose,
  onSelect,
}: {
  id: string;
  onClose: () => void;
  onSelect: (id: string) => void;
}) {
  const query = useJsonQuery<Row>(`${BASE}/questions/${id}`),
    action = useAction();
  const [editing, setEditing] = useState(false);
  const [number, setNumber] = useState<number | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const item = query.data;
  const version =
    item?.versions?.find((v: Row) => v.number === number) ||
    item?.versions?.[0];
  return (
    <section className="panel">
      <div className="wb-toolbar">
        <h2>题目详情</h2>
        <button onClick={onClose}>关闭详情</button>
      </div>
      <QueryState query={query}>
        <h3>{item?.title}</h3>
        <p>
          <Badge value={item?.kind || "standalone"} /> · {item?.source_system} ·{" "}
          <Badge value={item?.status || "draft"} />
        </p>
        <label>
          正文版本
          <select
            value={version?.number || ""}
            onChange={(e) => {
              setNumber(Number(e.target.value));
              setEditing(false);
            }}
          >
            {item?.versions?.map((v: Row) => (
              <option key={v.id} value={v.number}>
                v{v.number} · {v.published_at ? "正式" : "待人工确认"}
              </option>
            ))}
          </select>
        </label>
        <div className="wb-question">{version?.stem}</div>
        {version?.options?.map((o: string, i: number) => (
          <p key={i}>{o}</p>
        ))}
        <h4>参考答案</h4>
        <p className="wb-question">{version?.answer || "未提供"}</p>
        <h4>解析</h4>
        <p className="wb-question">{version?.explanation || "未提供"}</p>
        <p>
          {version?.tags?.map((t: Row) => t.name).join(" · ") ||
            "尚未绑定知识点与标签"}
        </p>
        {item?.parent_id && (
          <button onClick={() => onSelect(item.parent_id)}>
            查看父级材料 / 大题
          </button>
        )}
        {item?.children?.length > 0 && (
          <ul>
            {item?.children.map((child: Row) => (
              <li key={child.id}>
                <button onClick={() => onSelect(child.id)}>
                  {labels[child.kind]} · {child.title}
                </button>
              </li>
            ))}
          </ul>
        )}
        {canWrite() && item?.source_system === "native" && !item.deleted_at && (
          <>
            <button onClick={() => setEditing(!editing)}>
              以此正文创建新版本
            </button>
            {item.status === "draft" && (
              <div className="wb-toolbar">
                <label>
                  <input
                    type="checkbox"
                    checked={reviewed}
                    onChange={(e) => setReviewed(e.target.checked)}
                  />
                  已核对最新题干、答案与标签
                </label>
                <button
                  disabled={!reviewed || action.isPending}
                  onClick={() =>
                    action.mutate(
                      {
                        path: `/questions/${id}/publish`,
                        body: { expected_revision: item.revision },
                      },
                      { onSuccess: () => setReviewed(false) },
                    )
                  }
                >
                  确认发布最新版本
                </button>
              </div>
            )}
          </>
        )}
        <ActionError action={action} />
        {editing && item && (
          <QuestionForm
            key={`${id}-${version?.id}`}
            item={item}
            version={version}
            parents={[]}
            onSaved={() => {
              setEditing(false);
              setNumber(null);
            }}
          />
        )}
      </QueryState>
    </section>
  );
}
function Taxonomy() {
  const [deleted, setDeleted] = useState(false);
  const [editing, setEditing] = useState<Row | null>(null);
  const subjects = useSchoolOptions("subjects");
  const query = useJsonQuery<Row[]>(`${BASE}/taxonomy?deleted=${deleted}`);
  const action = useAction();
  const update = useAction("PUT");
  const life = useAction();
  const fields: Field[] = [
    { name: "name", label: "节点名称" },
    {
      name: "subject_id",
      label: "学科",
      type: "select",
      options: options(subjects.data?.items),
    },
    {
      name: "kind",
      label: "字典类型",
      type: "select",
      options: [
        "knowledge",
        "stage",
        "grade",
        "type",
        "difficulty",
        "ability",
        "tag",
      ].map((k) => ({ value: k, label: labels[k] })),
    },
    {
      name: "parent_id",
      label: "父节点",
      type: "select",
      required: false,
      options: options(query.data?.filter((r) => r.id !== editing?.id)),
    },
  ];
  const nodes = query.data || [];
  const render = (
    parent: string | null,
    visited = new Set<string>(),
  ): React.ReactNode => (
    <ul className="wb-tree">
      {nodes
        .filter((n) => (n.parent_id || null) === parent)
        .map((n) => (
          <li key={n.id}>
            <span>
              {n.name} <Badge value={n.kind} />
            </span>
            {canWrite() && (
              <>
                <button onClick={() => setEditing(n)}>编辑</button>
                <button
                  disabled={life.isPending}
                  onClick={() =>
                    life.mutate({
                      path: `/taxonomy/${n.id}/${deleted ? "restore" : "delete"}`,
                      body: {},
                    })
                  }
                >
                  {deleted ? "恢复" : "软删除（检查引用）"}
                </button>
              </>
            )}
            {!visited.has(n.id) && render(n.id, new Set([...visited, n.id]))}
          </li>
        ))}
    </ul>
  );
  return (
    <>
      <div className="wb-toolbar">
        <label>
          <input
            type="checkbox"
            checked={deleted}
            onChange={(e) => {
              setDeleted(e.target.checked);
              setEditing(null);
            }}
          />
          回收站
        </label>
        <p>父子须同学科、同类型；被题目或成绩引用的节点不可删除。</p>
      </div>
      <ActionError action={life} />
      <QueryState query={query} empty={!nodes.length}>
        {render(null)}
        {nodes
          .filter(
            (n) => n.parent_id && !nodes.some((p) => p.id === n.parent_id),
          )
          .map((n) => (
            <div key={n.id}>
              {n.name}（父节点在其他状态）
              <button
                disabled={!canWrite() || life.isPending}
                onClick={() =>
                  life.mutate({ path: `/taxonomy/${n.id}/restore`, body: {} })
                }
              >
                恢复
              </button>
            </div>
          ))}
      </QueryState>
      {canWrite() && !deleted && (
        <>
          <ActionError action={action} />
          <ActionError action={update} />
          <FormPanel
            key={editing?.id || "new-taxonomy"}
            title={editing ? "编辑知识点 / 标签" : "新建知识点 / 标签"}
            fields={fields}
            initial={editing || { kind: "knowledge" }}
            pending={action.isPending || update.isPending}
            onSubmit={(v) => {
              const body = { ...v, parent_id: v.parent_id || null };
              if (editing)
                update.mutate(
                  {
                    path: `/taxonomy/${editing.id}`,
                    body: { ...body, expected_revision: editing.revision },
                  },
                  { onSuccess: () => setEditing(null) },
                );
              else action.mutate({ path: "/taxonomy", body });
            }}
          />
          {editing && (
            <button onClick={() => setEditing(null)}>取消编辑</button>
          )}
        </>
      )}
    </>
  );
}
