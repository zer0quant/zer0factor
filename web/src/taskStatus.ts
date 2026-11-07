import type { TaskKind, TaskStatus } from "./types";

export const STATUS_LABEL: Record<TaskStatus, string> = {
  queued: "排队中",
  running: "运行中",
  succeeded: "成功",
  failed: "失败",
  cancelled: "已取消",
  lost: "中断",
};

/** antd Tag / Badge colours. */
export const STATUS_COLOR: Record<TaskStatus, string> = {
  queued: "default",
  running: "processing",
  succeeded: "success",
  failed: "error",
  cancelled: "warning",
  lost: "error",
};

export const KIND_LABEL: Record<TaskKind, string> = {
  evaluate: "评估",
  build: "构建",
  base: "基础因子",
  warm: "预热缓存",
};

export const isActive = (s: TaskStatus) => s === "queued" || s === "running";

export function fmtTime(iso: string | null | undefined): string {
  return iso ? iso.replace("T", " ").slice(5, 16) : "-";
}

export function duration(start: string | null, end: string | null): string {
  if (!start) return "-";
  const ms = (end ? new Date(end) : new Date()).getTime() - new Date(start).getTime();
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s} 秒`;
  if (s < 3600) return `${Math.floor(s / 60)} 分 ${s % 60} 秒`;
  return `${Math.floor(s / 3600)} 时 ${Math.floor((s % 3600) / 60)} 分`;
}
