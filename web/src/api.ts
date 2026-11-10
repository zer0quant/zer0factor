import type {
  BaseCurves,
  BaseInfo,
  BaseRow,
  BoardRow,
  CurveKind,
  Compare,
  CompareCurveKind,
  Correlation,
  Detail,
  EvalOptions,
  FactorInfo,
  Family,
  LatestValues,
  Meta,
  Task,
  TaskKind,
  TaskList,
  TaskLog,
} from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

const enc = encodeURIComponent;

export const fetchMeta = () => request<Meta>("/api/meta");
export const refresh = () => request<Meta>("/api/refresh", { method: "POST" });
export const fetchFactors = () => request<{ rows: BoardRow[] }>("/api/factors").then((r) => r.rows);
export const fetchBases = () => request<{ rows: BaseRow[] }>("/api/bases").then((r) => r.rows);
export const fetchBase = (base: string) => request<BaseInfo>(`/api/bases/${enc(base)}`);
export function fetchBaseCurves(
  base: string,
  q: { prep?: string; win?: number | null; kind: CurveKind },
): Promise<BaseCurves> {
  const p = new URLSearchParams({ kind: q.kind });
  if (q.prep !== undefined) p.set("prep", q.prep);
  else p.set("win", q.win == null ? "none" : String(q.win));
  return request<BaseCurves>(`/api/bases/${enc(base)}/curves?${p}`);
}
export const fetchFactor = (name: string) => request<FactorInfo>(`/api/factors/${enc(name)}`);
export const fetchDetail = (name: string, runId: string, period: string) =>
  request<Detail>(`/api/factors/${enc(name)}/runs/${enc(runId)}?period=${enc(period)}`);
export const fetchLatest = (name: string, runId: string, page: number, size: number, ascending = false) =>
  request<LatestValues>(
    `/api/factors/${enc(name)}/runs/${enc(runId)}/latest?page=${page}&size=${size}${ascending ? "&ascending=true" : ""}`,
  );
export const fetchCompare = (fs: string[], kind: CompareCurveKind = "long") =>
  request<Compare>(`/api/compare?f=${enc(fs.join(","))}&kind=${kind}`);
export const fetchCorrelation = (fs: string[]) =>
  request<Correlation>(`/api/compare/correlation?f=${enc(fs.join(","))}`);

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const fetchTasks = (opts: { status?: string[]; kind?: string; limit?: number } = {}) => {
  const q = new URLSearchParams();
  if (opts.status?.length) q.set("status", opts.status.join(","));
  if (opts.kind) q.set("kind", opts.kind);
  if (opts.limit) q.set("limit", String(opts.limit));
  return request<TaskList>(`/api/tasks?${q}`);
};
export const fetchTask = (id: string) => request<Task>(`/api/tasks/${enc(id)}`);
export const fetchTaskLog = (id: string, offset: number) =>
  request<TaskLog>(`/api/tasks/${enc(id)}/log?offset=${offset}`);
export const createTask = (kind: TaskKind, params: Record<string, unknown>) =>
  request<Task>("/api/tasks", json("POST", { kind, params }));
export const cancelTask = (id: string) => request<Task>(`/api/tasks/${enc(id)}/cancel`, json("POST"));
export const retryTask = (id: string) => request<Task>(`/api/tasks/${enc(id)}/retry`, json("POST"));
export const fetchEvalOptions = () => request<EvalOptions>("/api/eval/options");
export const fetchFamilies = (refresh = false) =>
  request<{ families: Family[]; scanned_at: string }>(`/api/families${refresh ? "?refresh=true" : ""}`);
export const patchFamily = (name: string, body: { status?: string; note?: string }) =>
  request<Family>(`/api/families/${enc(name)}`, json("PATCH", body));
