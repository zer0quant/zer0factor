import { Tag, Tooltip } from "antd";
import type { BaseStatus, Num } from "../types";

const TIP: Record<string, string> = {
  "1": "正向：因子值越大，未来收益越高",
  "-1": "反向：因子值越小，未来收益越高",
};

/** Direction of a base factor's primary version: 正向 (red) / 反向 (green), or why there is none. */
export function DirectionTag({ direction, status }: { direction: Num; status: BaseStatus }) {
  if (status === "mixed")
    return (
      <Tooltip title="主版本各窗口的评估方向不一致，逻辑不清楚">
        <Tag bordered={false} color="warning">
          方向不一致
        </Tag>
      </Tooltip>
    );
  if (status !== "ok" || (direction !== 1 && direction !== -1))
    return <span style={{ color: "var(--zf-muted)" }}>—</span>;
  return (
    <Tooltip title={TIP[String(direction)]}>
      <Tag bordered={false} color={direction === 1 ? "red" : "green"} style={{ marginInlineEnd: 0 }}>
        {direction === 1 ? "正向" : "反向"}
      </Tag>
    </Tooltip>
  );
}

export const STATUS_LABEL: Record<BaseStatus, string> = {
  ok: "",
  mixed: "方向不一致",
  unevaluated: "待评估",
  missing: "待中性化",
};
