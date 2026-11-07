import type {
  BoardRow,
  Compare,
  Correlation,
  Detail,
  FactorInfo,
  LatestValues,
  Meta,
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
