import { useEffect, useRef } from "react";

/** True when a key press should go to the focused control rather than a page shortcut. */
function typing(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null;
  if (!t) return false;
  if (t.isContentEditable) return true;
  const tag = t.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return !!t.closest(".ant-select, .ant-picker, [role='combobox'], [role='dialog'] input");
}

/**
 * Single-key page shortcuts (no modifiers). Ignored while typing in a field.
 * Handlers are read from a ref, so callers may pass a fresh object each render.
 */
export function useHotkeys(map: Record<string, (e: KeyboardEvent) => void>, enabled = true) {
  const ref = useRef(map);
  ref.current = map;
  useEffect(() => {
    if (!enabled) return;
    const on = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented || typing(e)) return;
      // Enter / Space on a focused button or link keeps its native meaning.
      if ((e.key === "Enter" || e.key === " ") && (e.target as HTMLElement | null)?.closest?.("button, a, [role='button']"))
        return;
      const fn = ref.current[e.key];
      if (fn) {
        e.preventDefault();
        fn(e);
      }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [enabled]);
}

/** Shortcut reference shown by the "?" help dialog. */
export const SHORTCUTS: [string, [string, string][]][] = [
  [
    "全局",
    [
      ["?", "显示快捷键"],
      ["/", "聚焦搜索框（看板）"],
    ],
  ],
  [
    "因子看板",
    [
      ["j / k", "下一行 / 上一行"],
      ["Enter 或 o", "打开详情（分组行：展开/收起）"],
      ["x", "勾选 / 取消对比"],
      ["c", "开始对比（对比篮 ≥ 2 个）"],
      ["v", "切换列表 / 矩阵"],
      ["g", "切换按族分组"],
    ],
  ],
  [
    "因子详情",
    [
      ["h / l", "同族上一个 / 下一个窗口"],
      ["a", "加入 / 移出对比"],
      ["b", "回到因子看板"],
    ],
  ],
];
