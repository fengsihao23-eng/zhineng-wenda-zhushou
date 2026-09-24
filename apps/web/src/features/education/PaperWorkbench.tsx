import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AppShell } from "../../layouts/AppShell";
import { useJsonQuery } from "../../hooks/useApi";
import { ErrorDisplay } from "../../components/ErrorDisplay";
import {
  BASE,
  Row,
  PageData,
  Badge,
  QueryState,
  ReadOnlyNote,
  canWrite,
  useAction,
  ActionError,
  FormPanel,
  Table,
  Pager,
  usePagination,
  HelpTip,
  useSchoolOptions,
  options,
  AssetUpload,
  AssetButton,
  assetUrl,
  labels,
} from "./shared";

export function PaperWorkbenchPage({ view = "list" }: { view?: "list" | "create" | "detail" }) {
  const pagination = usePagination();
  const { page, pageSize } = pagination;
  const { paperId: id = "" } = useParams();
  const navigate = useNavigate();
  const [asset, setAsset] = useState<Row | null>(null);
  const list = useJsonQuery<PageData>(`${BASE}/papers?page=${page}&page_size=${pageSize}`, view === "list"),
    exams = useSchoolOptions("exams"),
    subjects = useSchoolOptions("subjects"),
    action = useAction();
  return (
    <AppShell title={view === "create" ? "上传新试卷" : view === "detail" ? "试卷详情" : "试卷与原件"} eyebrow="业务生产 / 试卷版本">
      <ReadOnlyNote />
      <div className="wb-toolbar">
        {view !== "list" && <Link className="secondary-button" to="/admin/papers">返回试卷列表</Link>}
        {view === "list" && canWrite() && <Link className="primary-button" to="/admin/papers/new">上传新试卷</Link>}
        <HelpTip label="版本说明">替换原件会新增版本，已经引用的原件保持不变。</HelpTip>
      </div>
      {view === "list" && <>
      {list.data && !list.error && <Pager {...pagination} total={list.data.total} />}
      <QueryState query={list} empty={!list.data?.items.length}>
        <Table headers={["试卷", "来源", "状态", "操作"]}>
          {list.data?.items.map((p) => (
            <tr key={p.id}>
              <td>{p.title}</td>
              <td>{p.source_system}</td>
              <td>
                <Badge value={p.status} />
              </td>
              <td>
                <Link to={`/admin/papers/${p.id}`}>原件 / 版本 / 拆题</Link>
              </td>
            </tr>
          ))}
        </Table>
      </QueryState></>}
      {view === "create" && canWrite() && (
        <section className="panel">
          <h2>上传新试卷</h2>
          <AssetUpload onUploaded={setAsset} />
          {asset && (
            <>
              <p role="status">
                原件已保存：{asset.filename} · {asset.pages?.length} 页
              </p>
              <FormPanel
                key={asset.id}
                title="绑定考试与科目"
                fields={[
                  { name: "title", label: "试卷名称" },
                  {
                    name: "exam_id",
                    label: "考试",
                    type: "select",
                    options: options(exams.data?.items),
                  },
                  {
                    name: "subject_id",
                    label: "学科",
                    type: "select",
                    options: options(subjects.data?.items),
                  },
                ]}
                pending={action.isPending}
                onSubmit={(v) =>
                  action.mutate(
                    { path: "/papers", body: { ...v, asset_id: asset.id } },
                    {
                      onSuccess: (p) => {
                        setAsset(null);
                        navigate(`/admin/papers/${p.id}`);
                      },
                    },
                  )
                }
              />
            </>
          )}
          <ActionError action={action} />
        </section>
      )}
      {view === "detail" && id && <PaperDetail key={id} id={id} />}
    </AppShell>
  );
}
function PaperDetail({ id }: { id: string }) {
  const query = useJsonQuery<Row>(`${BASE}/papers/${id}`),
    action = useAction();
  const [replacement, setReplacement] = useState<Row | null>(null);
  return (
    <section className="panel">
      <QueryState query={query}>
        <h2>{query.data?.title}</h2>
        <Table paginate headers={["版本 / 时间", "原件", "操作"]}>
          {query.data?.versions?.map((v: Row) => (
            <tr key={v.id}>
              <td>
                v{v.number}
                <small className="subtle">{v.created_at?.slice(0, 16)}</small>
              </td>
              <td>
                {v.filename}
                <small className="subtle">
                  {v.pages?.length} 页 · {v.content_hash?.slice(0, 12)}
                </small>
              </td>
              <td>
                <AssetButton id={v.asset_id} />
                {query.data?.source_system === "native" && (
                  <Link to={`/admin/papers/${id}/split/${v.id}`}>
                    拆题工作台
                  </Link>
                )}
              </td>
            </tr>
          ))}
        </Table>
        {query.data?.source_system === "native" && canWrite() && (
          <>
            <AssetUpload
              label="上传替换原件（新版本）"
              onUploaded={setReplacement}
            />
            {replacement && (
              <div className="wb-toolbar">
                <span>{replacement.filename}</span>
                <button
                  disabled={action.isPending}
                  onClick={() =>
                    action.mutate(
                      {
                        path: `/papers/${id}/versions`,
                        body: {
                          asset_id: replacement.id,
                          expected_revision: query.data?.revision,
                        },
                      },
                      { onSuccess: () => setReplacement(null) },
                    )
                  }
                >
                  确认新增原件版本
                </button>
                <button onClick={() => setReplacement(null)}>取消</button>
              </div>
            )}
          </>
        )}
        <ActionError action={action} />
      </QueryState>
    </section>
  );
}

type Region = {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
};
type Entry = {
  key: string;
  parent_key: string | null;
  kind: string;
  title: string;
  stem: string;
  answer: string;
  explanation: string;
  options: string[];
  regions: Region[];
  tag_ids: string[];
};
export function PaperSplitPage() {
  const { paperId = "", versionId = "" } = useParams();
  const paper = useJsonQuery<Row>(`${BASE}/papers/${paperId}`),
    query = useJsonQuery<Row>(`${BASE}/paper-versions/${versionId}/draft`);
  const tags = useJsonQuery<Row[]>(`${BASE}/taxonomy`),
    save = useAction("PUT"),
    ocr = useAction(),
    publish = useAction();
  const [entries, setEntries] = useState<Entry[]>([]),
    [revision, setRevision] = useState(1),
    [dirty, setDirty] = useState(false),
    [selected, setSelected] = useState(""),
    [page, setPage] = useState(1),
    [zoom, setZoom] = useState(100),
    [image, setImage] = useState<string | null>(null),
    [imageError, setImageError] = useState<Error | null>(null),
    [imageAttempt, setImageAttempt] = useState(0),
    [confirmed, setConfirmed] = useState(false),
    [append, setAppend] = useState(false);
  const [drag, setDrag] = useState<{
    x: number;
    y: number;
    endX: number;
    endY: number;
  } | null>(null);
  const entriesRef = useRef(entries);
  entriesRef.current = entries;
  const loaded = useRef(false),
    canvas = useRef<HTMLDivElement>(null);
  const version = paper.data?.versions?.find((v: Row) => v.id === versionId);
  const frozen = query.data?.published_revision != null;
  const editable = canWrite() && !frozen;
  useEffect(() => {
    if (query.data && !loaded.current) {
      setEntries(query.data.entries);
      setRevision(query.data.revision);
      setSelected(query.data.entries[0]?.key || "");
      loaded.current = true;
    }
  }, [query.data]);
  useEffect(() => {
    if (!version?.asset_id) return;
    let active = true;
    let url: string | undefined;
    setImage(null);
    setImageError(null);
    assetUrl(version.asset_id, page)
      .then((value) => {
        url = value;
        if (active) setImage(value);
        else URL.revokeObjectURL(value);
      })
      .catch((e) => {
        if (active) setImageError(e);
      });
    return () => {
      active = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [version?.asset_id, page, imageAttempt]);
  const persist = () => {
    if (save.isPending || !dirty || !editable) return;
    const snapshot = JSON.stringify(entriesRef.current);
    save.mutate(
      {
        path: `/paper-versions/${versionId}/draft`,
        body: { entries: entriesRef.current, expected_revision: revision },
      },
      {
        onSuccess: (r) => {
          setRevision(r.revision);
          if (JSON.stringify(entriesRef.current) === snapshot) setDirty(false);
        },
      },
    );
  };
  useEffect(() => {
    if (!dirty || !editable || save.isPending || save.error) return;
    const timer = setTimeout(persist, 1200);
    return () => clearTimeout(timer);
  }, [entries, dirty, editable, revision, save.isPending, save.error]);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const jobs = (query.data?.jobs || []) as Row[];
  useEffect(() => {
    if (!jobs.some((j) => ["running", "queued"].includes(j.status))) return;
    const timer = setInterval(() => {
      void query.refetch();
    }, 1500);
    return () => clearInterval(timer);
  }, [jobs.map((j) => j.status).join(","), query.refetch]);
  const updateEntries = (next: Entry[]) => {
    setEntries(next);
    setDirty(true);
    setConfirmed(false);
    save.reset();
  };
  const current = entries.find((e) => e.key === selected);
  const edit = (change: Partial<Entry>) =>
    updateEntries(
      entries.map((e) => (e.key === selected ? { ...e, ...change } : e)),
    );
  const regionAdded = (region: Region) => {
    if (!editable) return;
    if (append && current) {
      edit({ regions: [...current.regions, region] });
      return;
    }
    const key = crypto.randomUUID();
    updateEntries([
      ...entries,
      {
        key,
        parent_key: null,
        kind: "standalone",
        title: `第 ${entries.length + 1} 题`,
        stem: "",
        answer: "",
        explanation: "",
        options: [],
        regions: [region],
        tag_ids: [],
      },
    ]);
    setSelected(key);
  };
  const position = (event: React.PointerEvent) => {
    const bounds = canvas.current!.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
      y: Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)),
    };
  };
  const finish = () => {
    if (!drag) return;
    const region = {
      page,
      x: Math.min(drag.x, drag.endX),
      y: Math.min(drag.y, drag.endY),
      width: Math.abs(drag.endX - drag.x),
      height: Math.abs(drag.endY - drag.y),
    };
    setDrag(null);
    if (region.width > 0.005 && region.height > 0.005) regionAdded(region);
  };
  return (
    <AppShell title="框选拆题工作台" eyebrow="试卷 / 原件—区域—草稿—确认">
      <Link to="/admin/papers">返回试卷</Link>
      <p className="wb-mobile-readonly">
        手机提供原件与草稿只读查看。框选、编辑和发布请使用宽屏设备。
      </p>
      <QueryState query={paper}>
        <QueryState query={query}>
          <div className="wb-toolbar">
            <strong>
              {paper.data?.title} · 原件 v{version?.number}
            </strong>
            <span role="status">
              {save.isPending
                ? "正在保存…"
                : dirty
                  ? "有未保存修改"
                  : `草稿已保存 · 修订 ${revision}`}
            </span>
            {frozen && <Badge value="published" />}
            <button
              className="wb-desktop-edit"
              disabled={!dirty || save.isPending || !editable}
              onClick={persist}
            >
              立即保存草稿
            </button>
            {save.error && (
              <button
                onClick={() => {
                  loaded.current = false;
                  setDirty(false);
                  void query.refetch();
                }}
              >
                放弃本地修改，重读服务端草稿
              </button>
            )}
          </div>
          <ActionError action={save} />
          <ActionError action={ocr} />
          <ActionError action={publish} />
          <div className="wb-split">
            <section className="panel">
              <h2>题目区域</h2>
              <div className="wb-region-list">
                {entries.length ? (
                  entries.map((e) => (
                    <button
                      key={e.key}
                      className={selected === e.key ? "active" : ""}
                      onClick={() => {
                        setSelected(e.key);
                        setPage(e.regions[0]?.page || 1);
                      }}
                    >
                      {labels[e.kind]} · {e.title}
                      <small> {e.regions.length} 个区域</small>
                    </button>
                  ))
                ) : (
                  <p>暂无区域。在原图拖动框选，或使用键盘新增区域。</p>
                )}
              </div>
              <button
                className="wb-desktop-edit"
                disabled={!editable}
                onClick={() =>
                  regionAdded({ page, x: 0.1, y: 0.1, width: 0.8, height: 0.2 })
                }
              >
                新增可编辑区域
              </button>
              <label className="wb-desktop-edit">
                <input
                  type="checkbox"
                  disabled={!editable || !current}
                  checked={append}
                  onChange={(e) => setAppend(e.target.checked)}
                />
                继续框选当前题（跨页）
              </label>
            </section>
            <section>
              <div className="wb-toolbar">
                <label>
                  页码
                  <select
                    aria-label="页码"
                    value={page}
                    onChange={(e) => setPage(Number(e.target.value))}
                  >
                    {version?.pages?.map((p: Region) => (
                      <option key={p.page} value={p.page}>
                        第 {p.page} 页
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  缩放
                  <select
                    aria-label="缩放"
                    value={zoom}
                    onChange={(e) => setZoom(Number(e.target.value))}
                  >
                    {[75, 100, 150, 200].map((z) => (
                      <option key={z} value={z}>
                        {z}%
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <ErrorDisplay
                error={imageError}
                onRetry={() => setImageAttempt((n) => n + 1)}
              />
              {!image && !imageError && <p>正在受权读取原图…</p>}
              <div className="wb-canvas-scroll">
                <div
                  className="wb-canvas"
                  ref={canvas}
                  style={{ width: `${zoom}%` }}
                  onPointerDown={(e) => {
                    if (!image || !editable || window.innerWidth < 768) return;
                    e.currentTarget.setPointerCapture(e.pointerId);
                    const p = position(e);
                    setDrag({ ...p, endX: p.x, endY: p.y });
                  }}
                  onPointerMove={(e) => {
                    if (drag) {
                      const p = position(e);
                      setDrag({ ...drag, endX: p.x, endY: p.y });
                    }
                  }}
                  onPointerUp={finish}
                  onPointerCancel={() => setDrag(null)}
                >
                  {image && <img src={image} alt={`试卷原件第 ${page} 页`} />}{" "}
                  {entries.flatMap((entry) =>
                    entry.regions
                      .filter((r) => r.page === page)
                      .map((r, i) => (
                        <div
                          key={`${entry.key}-${i}`}
                          className="wb-region"
                          style={{
                            left: `${r.x * 100}%`,
                            top: `${r.y * 100}%`,
                            width: `${r.width * 100}%`,
                            height: `${r.height * 100}%`,
                            borderColor:
                              entry.key === selected ? "#bd4b30" : undefined,
                          }}
                        >
                          <span>{entry.title}</span>
                        </div>
                      )),
                  )}
                  {drag && (
                    <div
                      className="wb-region"
                      style={{
                        left: `${Math.min(drag.x, drag.endX) * 100}%`,
                        top: `${Math.min(drag.y, drag.endY) * 100}%`,
                        width: `${Math.abs(drag.endX - drag.x) * 100}%`,
                        height: `${Math.abs(drag.endY - drag.y) * 100}%`,
                      }}
                    />
                  )}
                </div>
              </div>
            </section>
            <section className="panel">
              <h2>草稿属性</h2>
              {current ? (
                <>
                  <div className="wb-question wb-mobile-readonly">
                    {current.stem || "尚未录入题干"}
                  </div>
                  <div className="wb-form wb-desktop-edit">
                    <label>
                      层级
                      <select
                        aria-label="层级"
                        disabled={!editable}
                        value={current.kind}
                        onChange={(e) =>
                          edit({ kind: e.target.value, parent_key: null })
                        }
                      >
                        {["material", "major", "minor", "standalone"].map(
                          (k) => (
                            <option key={k} value={k}>
                              {labels[k]}
                            </option>
                          ),
                        )}
                      </select>
                    </label>
                    <label>
                      父级
                      <select
                        aria-label="父级"
                        disabled={
                          !editable ||
                          ["material", "standalone"].includes(current.kind)
                        }
                        value={current.parent_key || ""}
                        onChange={(e) =>
                          edit({ parent_key: e.target.value || null })
                        }
                      >
                        <option value="">无父级</option>
                        {entries
                          .slice(0, entries.indexOf(current))
                          .filter((e) =>
                            current.kind === "minor"
                              ? e.kind === "major"
                              : e.kind === "material",
                          )
                          .map((e) => (
                            <option key={e.key} value={e.key}>
                              {e.title}
                            </option>
                          ))}
                      </select>
                    </label>
                    {(["title", "stem", "answer", "explanation"] as const).map(
                      (field) => (
                        <label key={field}>
                          {
                            {
                              title: "名称",
                              stem: "题干",
                              answer: "参考答案",
                              explanation: "解析",
                            }[field]
                          }
                          <textarea
                            disabled={!editable}
                            aria-label={({ title: '名称', stem: '题干', answer: '参考答案', explanation: '解析' })[field]}
                            value={current[field]}
                            onChange={(e) => edit({ [field]: e.target.value })}
                          />
                        </label>
                      ),
                    )}
                    <label>
                      选项（每行一个）
                      <textarea
                        disabled={!editable}
                        aria-label="选项（每行一个）"
                        value={current.options.join("\n")}
                        onChange={(e) =>
                          edit({ options: e.target.value.split("\n") })
                        }
                      />
                    </label>
                    <fieldset>
                      <legend>区域坐标（0–1，可键盘修改）</legend>
                      {current.regions.map((region, i) => (
                        <div key={i}>
                          <strong>第 {region.page} 页</strong>
                          {(["x", "y", "width", "height"] as const).map(
                            (field) => (
                              <label key={field}>
                                {field}
                                <input
                                  aria-label={`区域${i + 1} ${field}`}
                                  type="number"
                                  step=".01"
                                  min="0"
                                  max="1"
                                  disabled={!editable}
                                  value={region[field]}
                                  onChange={(e) =>
                                    edit({
                                      regions: current.regions.map((r, j) =>
                                        j === i
                                          ? {
                                              ...r,
                                              [field]: Number(e.target.value),
                                            }
                                          : r,
                                      ),
                                    })
                                  }
                                />
                              </label>
                            ),
                          )}
                        </div>
                      ))}
                    </fieldset>
                    <fieldset>
                      <legend>知识点标签</legend>
                      {tags.data
                        ?.filter((t) => t.subject_id === paper.data?.subject_id)
                        .map((t) => (
                          <label key={t.id}>
                            <input
                              type="checkbox"
                              disabled={!editable}
                              checked={current.tag_ids.includes(t.id)}
                              onChange={(e) =>
                                edit({
                                  tag_ids: e.target.checked
                                    ? [...current.tag_ids, t.id]
                                    : current.tag_ids.filter(
                                        (id) => id !== t.id,
                                      ),
                                })
                              }
                            />
                            {t.name}
                          </label>
                        ))}
                    </fieldset>
                    <button
                      className="wb-danger"
                      disabled={
                        !editable ||
                        entries.some((e) => e.parent_key === current.key)
                      }
                      onClick={() => {
                        updateEntries(
                          entries.filter((e) => e.key !== current.key),
                        );
                        setSelected("");
                      }}
                    >
                      移除当前草稿区域
                    </button>
                  </div>
                </>
              ) : (
                <p>选择区域后编辑；OCR 结果须人工核对。</p>
              )}
            </section>
          </div>
          <section className="panel">
            <h2>识别任务与确认</h2>
            <p>{query.data?.ocr?.message}</p>
            <div className="wb-toolbar wb-desktop-edit">
              <button
                disabled={
                  !editable ||
                  dirty ||
                  save.isPending ||
                  ocr.isPending ||
                  !entries.length
                }
                onClick={() =>
                  ocr.mutate(
                    {
                      path: `/paper-versions/${versionId}/ocr`,
                      body: { expected_revision: revision },
                    },
                    {
                      onSuccess: () => {
                        void query.refetch();
                      },
                    },
                  )
                }
              >
                发起 OCR / 失败重试
              </button>
              <label>
                <input
                  type="checkbox"
                  disabled={dirty || !editable}
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                已逐题核对当前保存版本
              </label>
              <button
                disabled={
                  !editable ||
                  dirty ||
                  save.isPending ||
                  !confirmed ||
                  publish.isPending ||
                  !entries.length ||
                  entries.some((e) => !e.stem.trim())
                }
                onClick={() =>
                  publish.mutate(
                    {
                      path: `/paper-versions/${versionId}/publish`,
                      body: { expected_revision: revision, reviewed: true },
                    },
                    {
                      onSuccess: () => {
                        setConfirmed(false);
                        void query.refetch();
                      },
                    },
                  )
                }
              >
                人工确认并发布
              </button>
            </div>
            {jobs.length ? (
              jobs.map((job) => (
                <article key={job.id}>
                  <p>
                    <Badge value={job.status} /> · 第 {job.attempt} 次 ·
                    草稿修订 {job.draft_revision}
                    {job.error_code && ` · ${job.error_code}`}
                  </p>
                  {job.status === "running" && (
                    <progress aria-label="OCR 任务进度" />
                  )}
                  {job.result?.length > 0 && <button className="wb-desktop-edit" disabled={!editable || dirty || revision !== job.draft_revision} onClick={() => updateEntries(entries.map(entry => { const result = job.result.find((r: Row) => r.key === entry.key); return result ? { ...entry, stem: result.text } : entry }))}>将本次识别结果全部放入草稿</button>}
                  {job.result?.map((r: Row) => (
                    <div key={r.key}>
                      <p className="wb-question">
                        {r.text || "未识别出文本，请人工录入"}
                      </p>
                      <button
                        className="wb-desktop-edit"
                        disabled={
                          !editable || dirty || revision !== job.draft_revision
                        }
                        onClick={() =>
                          updateEntries(
                            entries.map((e) =>
                              e.key === r.key ? { ...e, stem: r.text } : e,
                            ),
                          )
                        }
                      >
                        将识别文本放入草稿（需再次确认）
                      </button>
                    </div>
                  ))}
                </article>
              ))
            ) : (
              <p>暂无 OCR 任务。可直接人工录入后保存。</p>
            )}
            {frozen && (
              <p role="status">
                已发布 {query.data?.published_ids?.length} 道题。
                <Link to="/admin/questions">进入题库回读</Link>
              </p>
            )}
          </section>
        </QueryState>
      </QueryState>
    </AppShell>
  );
}
