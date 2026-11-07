import type {
  BoardRow,
  Compare,
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
export const fetchFactors = () =>
  request<{ rows: BoardRow[] }>("/api/factors").then((r) => r.rows);
export const fetchFactor = (name: string) => request<FactorInfo>(`/api/factors/${enc(name)}`);
export const fetchDetail = (name: string, runId: string, period: string) =>
  request<Detail>(`/api/factors/${enc(name)}/runs/${enc(runId)}?period=${enc(period)}`);
export const fetchLatest = (name: string, runId: string, page: number, size: number) =>
  request<LatestValues>(
    `/api/factors/${enc(name)}/runs/${enc(runId)}/latest?page=${page}&size=${size}`,
  );
export const fetchBoardCurves = () =>
  request<{ points: number; items: Record<string, { cached: boolean; ls: (number | null)[] | null }> }>(
    "/api/board/curves",
  );
export const fetchCompare = (fs: string[]) =>
  request<Compare>(`/api/compare?f=${enc(fs.join(","))}`);
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
