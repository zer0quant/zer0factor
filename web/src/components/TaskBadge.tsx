import { useEffect, useRef } from "react";
import { Badge, Button, Empty, Popover, Progress, Space, Tag, Typography, notification } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchTasks } from "../api";
import { STATUS_COLOR, STATUS_LABEL, isActive } from "../taskStatus";
import type { Task } from "../types";

const POLL_MS = 3000;
/** Task kinds whose completion changes what the board shows. */
const REFRESHING = new Set(["evaluate", "warm"]);

export function TaskProgress({ task, size = "small" }: { task: Task; size?: "small" | "default" }) {
  if (task.status === "running" && task.progress_total) {
    return (
      <Progress
        size={size}
        percent={Math.round((100 * task.progress_done) / task.progress_total)}
        format={() => `${task.progress_done}/${task.progress_total}`}
      />
    );
  }
  return <Tag color={STATUS_COLOR[task.status]}>{STATUS_LABEL[task.status]}</Tag>;
}

/**
 * Header badge with the number of running tasks. It also watches tasks finish: when an
 * evaluation or cache warm-up ends, board data is re-fetched and a notification is shown.
 */
export function TaskBadge() {
  const client = useQueryClient();
  const tasks = useQuery({
    queryKey: ["tasks", "recent"],
    queryFn: () => fetchTasks({ limit: 30 }),
    refetchInterval: POLL_MS,
    staleTime: 0,
  });
  const prevActive = useRef<Set<string> | null>(null);

  useEffect(() => {
    const list = tasks.data?.tasks;
    if (!list) return;
    const active = new Set(list.filter((t) => isActive(t.status)).map((t) => t.id));
    const prev = prevActive.current;
    prevActive.current = active;
    if (!prev) return;
    const finished = list.filter((t) => prev.has(t.id) && !active.has(t.id));
    if (!finished.length) return;
    client.invalidateQueries({ queryKey: ["tasks"] });
    client.invalidateQueries({ queryKey: ["families"] });
    if (finished.some((t) => REFRESHING.has(t.kind))) {
      for (const key of ["meta", "factors", "board-curves", "factor", "detail"]) {
        client.invalidateQueries({ queryKey: [key] });
      }
    }
    for (const t of finished) {
      const ok = t.status === "succeeded";
      notification[ok ? "success" : t.status === "cancelled" ? "info" : "error"]({
        message: `${t.title}：${STATUS_LABEL[t.status]}`,
        description: (
          <Link to={`/tasks/${t.id}`}>{ok && t.kind === "evaluate" ? "看板数据已刷新，查看任务" : "查看任务"}</Link>
        ),
        placement: "bottomRight",
      });
    }
  }, [tasks.data, client]);

  const running = tasks.data?.running ?? 0;
  const queued = tasks.data?.queued ?? 0;
  const recent = (tasks.data?.tasks ?? []).slice(0, 5);

  const content = (
    <div style={{ width: 320 }}>
      {recent.length ? (
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          {recent.map((t) => (
            <div key={t.id}>
              <Link to={`/tasks/${t.id}`}>
                <Typography.Text ellipsis style={{ maxWidth: 300 }}>
                  {t.title}
                </Typography.Text>
              </Link>
              <TaskProgress task={t} />
            </div>
          ))}
        </Space>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有任务" />
      )}
      <div style={{ marginTop: 12, textAlign: "right" }}>
        <Link to="/tasks">全部任务</Link>
      </div>
    </div>
  );

  return (
    <Popover
      content={content}
      title={running || queued ? `运行中 ${running} · 排队 ${queued}` : "任务"}
      trigger="click"
      placement="bottomRight"
    >
      <Badge count={running} size="small" offset={[-2, 2]}>
        <Button size="small" aria-label="任务">
          任务
        </Button>
      </Badge>
    </Popover>
  );
}
