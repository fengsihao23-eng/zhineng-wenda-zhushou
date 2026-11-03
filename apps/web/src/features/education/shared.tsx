import { Children, useEffect, useId, useRef, useState, type ReactNode, type FormEvent } from "react";
import { HelpTip } from "../../components/HelpTip";
import { ListView } from "../../components/ListControls";
export { Pagination as Pager, usePagination, useClientPagination } from "../../components/ListControls";
export { HelpTip } from "../../components/HelpTip";
import { useApiMutation, useJsonQuery } from "../../hooks/useApi";
import { apiFetch, apiError } from "../../services/api";
import { getUserInfo } from "../../utils/auth";
import { ErrorDisplay } from "../../components/ErrorDisplay";
import "./workbench.css";

export const BASE = "/platform/education";
export type Row = Record<string, any> & { id: string };
export type PageData = { items: Row[]; total: number };
export const canWrite = () =>
  (getUserInfo()?.roles || []).some((r) =>
    ["SCHOOL_ADMIN", "SUPER_ADMIN"].includes(r.toUpperCase()),
  );
export const labels: Record<string, string> = {
  active: "有效",
  inactive: "已停用",
  departed: "已离职",
  suspended: "已休学",
  withdrawn: "已退学",
  graduated: "已毕业归档",
  draft: "草稿",
  published: "正式",
  uploaded: "已上传",
  invalid: "预检未通过",
  ready: "待确认",
  running: "处理中",
  succeeded: "已完成",
  failed: "失败",
  queued: "排队中",
  open: "待接单",
  accepted: "处理中",
  resolved: "已解决",
  closed: "已关闭",
  learning: "学习中",
  reviewing: "复习中",
  mastered: "自评已掌握",
  material: "材料",
  major: "大题",
  minor: "小题",
  standalone: "独立题",
  knowledge: "知识点",
  stage: "学段",
  grade: "年级",
  type: "题型",
  difficulty: "难度",
  ability: "能力",
  tag: "标签",
};
export function Badge({ value }: { value: string }) {
  return (
    <span className={`wb-badge wb-badge--${value}`}>
      {labels[value] || value}
    </span>
  );
}
export function QueryState({
  query,
  empty,
  children,
}: {
  query: { isLoading: boolean; error: Error | null; refetch: () => unknown };
  empty?: boolean;
  children: ReactNode;
}) {
  if (query.isLoading)
    return (
      <p role="status" className="inline-empty">
        正在读取…
      </p>
    );
  if (query.error)
    return (
      <ErrorDisplay
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  if (empty)
    return (
      <p className="inline-empty">
        当前范围暂无记录。请调整筛选或完成数据接入。
      </p>
    );
  return <>{children}</>;
}
export function ReadOnlyNote() {
  return canWrite() ? null : (
    <HelpTip label="只读权限">当前角色只有读取权限，写入操作由学校管理员执行。</HelpTip>
  );
}
export function useAction<T = Row>(method: "POST" | "PUT" | "PATCH" = "POST") {
  return useApiMutation<T, { path: string; body: unknown }>(
    (v) => `${BASE}${v.path}`,
    method,
    { serialize: (v) => v.body },
  );
}
export function ActionError({
  action,
}: {
  action: { error: Error | null; reset: () => void };
}) {
  return (
    <ErrorDisplay
      error={action.error}
      title="操作未完成"
      onDismiss={action.reset}
      variant="banner"
    />
  );
}

/** Import confirm is asynchronous: poll the batch instead of holding a slow HTTP request. */
const IMPORT_TERMINAL = ["succeeded", "failed", "invalid"];

export async function pollRosterImport(
  id: string,
  onUpdate: (batch: Row) => void,
  stopped: () => boolean,
): Promise<Row> {
  const started = Date.now();
  while (Date.now() - started < 20 * 60 * 1000) {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    if (stopped()) throw new DOMException("请求已取消", "AbortError");
    // Status-only polling keeps a 1,448-row batch from being downloaded every tick.
    const response = await apiFetch(`${BASE}/roster/imports/${id}?progress=true`);
    if (!response.ok) throw await apiError(response, "读取入库进度失败");
    const next = (await response.json()) as Row;
    onUpdate(next);
    if (IMPORT_TERMINAL.includes(next.status)) {
      const detail = await apiFetch(`${BASE}/roster/imports/${id}`);
      if (!detail.ok) throw await apiError(detail, "读取入库结果失败");
      const final = (await detail.json()) as Row;
      onUpdate(final);
      return final;
    }
  }
  throw new Error("入库仍在后台执行，请稍后到操作记录查看结果。");
}

export function useImportPolling(
  batch: Row | null,
  onBatch: (batch: Row) => void,
  onDone?: (batch: Row) => void,
) {
  const [error, setError] = useState<Error | null>(null);
  const update = useRef(onBatch);
  const done = useRef(onDone);
  update.current = onBatch;
  done.current = onDone;
  useEffect(() => {
    if (!batch || batch.status !== "running") return;
    let stopped = false;
    setError(null);
    void pollRosterImport(batch.id, (next) => update.current(next), () => stopped)
      .then((final) => {
        if (!stopped) done.current?.(final);
      })
      .catch((reason) => {
        if (!stopped && (reason as Error)?.name !== "AbortError") setError(reason as Error);
      });
    return () => {
      stopped = true;
    };
    // The batch id/status are the only transitions that start or stop polling.
  }, [batch?.id, batch?.status]);
  return error;
}

export function ImportRunning({ batch, error }: { batch: Row; error?: Error | null }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  const total = batch.report?.progress?.total ?? batch.report?.total_rows ?? 0;
  return (
    <div role="status" className="teacher-alert teacher-alert--warn">
      <strong>正在整批入库，请稍候</strong>
      <p>
        共 {total} 行，已等待 {elapsed} 秒。数据在服务器后台写入，可以暂时切到其他页面，但请勿重复点击或重复上传。
      </p>
      {error && <p>{error.message}</p>}
    </div>
  );
}

export function ImportFailure({ batch }: { batch: Row }) {
  const message = batch.report?.failed_reason || "入库未完成，未写入任何档案，可重新提交。";
  return <ErrorDisplay error={new Error(message)} title="入库未完成" variant="banner" />;
}
export function Table({
  headers,
  children,
  paginate = false,
}: {
  headers: string[];
  children: ReactNode;
  paginate?: boolean;
}) {
  if (paginate) return <ListView items={Children.toArray(children)}>{rows => <Table headers={headers}>{rows}</Table>}</ListView>;
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
export type Field = {
  name: string;
  label: string;
  type?:
    | "text"
    | "number"
    | "textarea"
    | "select"
    | "date"
    | "datetime-local"
    | "checkbox";
  required?: boolean;
  options?: { value: string; label: string }[];
  min?: number;
  max?: number;
  step?: string;
  maxLength?: number;
  hint?: string;
};
export function FormPanel({
  title,
  fields,
  initial = {},
  onSubmit,
  pending,
  submit = "保存",
  children,
}: {
  title: string;
  fields: Field[];
  initial?: Record<string, any>;
  onSubmit: (data: Record<string, any>) => void;
  pending: boolean;
  submit?: string;
  children?: ReactNode;
}) {
  const formId = useId();
  const [values, setValues] = useState<Record<string, any>>(() =>
    Object.fromEntries(
      fields
        .filter((f) => initial[f.name] !== undefined)
        .map((f) => [f.name, initial[f.name]]),
    ),
  );
  const send = (event: FormEvent) => {
    event.preventDefault();
    if (!pending) onSubmit(values);
  };
  return (
    <form className="panel wb-form" onSubmit={send}>
      <h2>{title}</h2>
      {fields.map((field) => (
        <div className="form-field" key={field.name}>
          <div><label htmlFor={`${formId}-${field.name}`}>{field.label}</label> {field.hint && <HelpTip label={`${field.label}说明`}>{field.hint}</HelpTip>}</div>
          {field.type === "select" ? (
            <select
              id={`${formId}-${field.name}`}
              aria-label={field.label}
              required={field.required !== false}
              value={values[field.name] ?? ""}
              onChange={(e) =>
                setValues({ ...values, [field.name]: e.target.value })
              }
            >
              <option value="">
                请选择{field.required === false ? "（可留空）" : ""}
              </option>
              {field.options?.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          ) : field.type === "textarea" ? (
            <textarea
              id={`${formId}-${field.name}`}
              aria-label={field.label}
              maxLength={field.maxLength || 50000}
              required={field.required !== false}
              value={values[field.name] ?? ""}
              onChange={(e) =>
                setValues({ ...values, [field.name]: e.target.value })
              }
            />
          ) : (
            <input
              id={`${formId}-${field.name}`}
              aria-label={field.label}
              type={field.type || "text"}
              maxLength={field.maxLength || 200}
              min={field.min}
              max={field.max}
              step={field.step}
              required={field.required !== false}
              value={values[field.name] ?? ""}
              onChange={(e) =>
                setValues({
                  ...values,
                  [field.name]:
                    field.type === "number"
                      ? e.target.value === ""
                        ? ""
                        : Number(e.target.value)
                      : e.target.value,
                })
              }
            />
          )}
        </div>
      ))}
      {children}
      <button className="primary-button" disabled={pending}>
        {pending ? "正在保存…" : submit}
      </button>
    </form>
  );
}
export function useSchoolOptions(kind: string) {
  return useJsonQuery<PageData>(`${BASE}/school/${kind}?page_size=100`);
}
export const options = (rows: Row[] | undefined, label = "name") =>
  (rows || []).map((r) => ({ value: r.id, label: String(r[label] || r.id) }));
export async function fileBase64(file: File): Promise<string> {
  if (file.size > 15 * 1024 * 1024) throw new Error("文件不能超过 15 MB。");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("无法读取文件，请重新选择"));
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.readAsDataURL(file);
  });
}
export function AssetUpload({
  onUploaded,
  label = "上传原件",
}: {
  onUploaded: (asset: Row) => void;
  label?: string;
}) {
  const action = useAction();
  const [file, setFile] = useState<File | null>(null);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const upload = async () => {
    if (!file || reading || action.isPending) return;
    setReading(true);
    setError(null);
    try {
      const content = await fileBase64(file);
      action.mutate(
        {
          path: "/assets",
          body: { filename: file.name, content_base64: content },
        },
        { onSuccess: onUploaded },
      );
    } catch (e) {
      setError(e as Error);
    } finally {
      setReading(false);
    }
  };
  return (
    <div className="wb-upload">
      <label>
        {label}
        <input
          aria-label={label}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          disabled={reading || action.isPending}
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
      </label>
      <HelpTip label="文件要求">PDF、PNG 或 JPEG；最大 15 MB、100 页。每次替换新增版本。</HelpTip>
      <button
        type="button"
        disabled={!file || reading || action.isPending}
        onClick={() => {
          void upload();
        }}
      >
        {reading
          ? "正在读取文件…"
          : action.isPending
            ? "正在校验并保存…"
            : "校验并上传"}
      </button>
      <ErrorDisplay error={error} />
      <ActionError action={action} />
    </div>
  );
}
export async function assetUrl(id: string, page?: number) {
  const response = await apiFetch(
    `${BASE}/assets/${id}${page ? `?page=${page}` : ""}`,
  );
  if (!response.ok) throw await apiError(response, "原件读取失败");
  return URL.createObjectURL(await response.blob());
}
export function AssetButton({
  id,
  label = "查看原件",
}: {
  id: string;
  label?: string;
}) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url) }, [url]);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const close = () => {
    if (url) URL.revokeObjectURL(url);
    setUrl(null);
  };
  const open = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      close();
      setUrl(await assetUrl(id));
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button
        type="button"
        onClick={() => {
          void open();
        }}
        disabled={busy}
      >
        {busy ? "正在校验权限…" : label}
      </button>
      <ErrorDisplay
        error={error}
        onRetry={() => {
          void open();
        }}
      />
      {url && (
        <div className="wb-preview">
          <div className="wb-toolbar">
            <a href={url} download="原件">
              下载当前版本
            </a>
            <button onClick={close}>关闭预览</button>
          </div>
          <iframe title="原件预览" src={url} sandbox="allow-same-origin" />

        </div>
      )}
    </>
  );
}
