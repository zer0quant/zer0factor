import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Grid,
  List,
  Modal,
  Segmented,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { cancelTask, fetchTask, fetchTaskLog, fetchTasks, retryTask } from "../api";
import { factorHref } from "../factorName";
import { TaskProgress } from "../components/TaskBadge";
import { ErrorState } from "../components/states";
import { KIND_LABEL, STATUS_COLOR, STATUS_LABEL, duration, fmtTime, isActive } from "../taskStatus";
import type { Task, TaskKind, TaskStatus } from "../types";

const LIST_POLL_MS = 3000;
const LOG_POLL_MS = 2000;
/** Keep the in-page log bounded; older text is dropped from the view (the file keeps it). */
const MAX_LOG_CHARS = 2_000_000;

type StatusFilter = "all" | "active" | "done" | "failed";
const STATUS_FILTERS: Record<StatusFilter, TaskStatus[] | undefined> = {
  all: undefined,
  active: ["queued", "running"],
  done: ["succeeded"],
  failed: ["failed", "lost", "cancelled"],
};

function TaskLog({ task }: { task: Task }) {
  const [text, setText] = useState("");
  const offset = useRef(0);
  const box = useRef<HTMLPreElement>(null);
  const follow = useRef(true);
  const [truncated, setTruncated] = useState(false);
  const active = isActive(task.status);

  useEffect(() => {
    setText("");
    setTruncated(false);
    offset.current = 0;
    follow.current = true;
  }, [task.id]);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const pull = async () => {
      try {
        // Drain everything available, then wait; a finished task stops after one drain.
        for (;;) {
          const chunk = await fetchTaskLog(task.id, offset.current);
          if (stopped) return;
          if (chunk.text) {
            offset.current = chunk.offset;
            setText((t) => {
              const next = t + chunk.text;
              if (next.length > MAX_LOG_CHARS) {
                setTruncated(true);
                return next.slice(next.length - MAX_LOG_CHARS);
              }
              return next;
            });
          }
          if (chunk.offset >= chunk.size) break;
        }
      } catch {
        /* transient: try again on the next tick */
      }
      if (!stopped && active) timer = setTimeout(pull, LOG_POLL_MS);
    };
    pull();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [task.id, active]);

  useEffect(() => {
    const el = box.current;
    if (el && follow.current) el.scrollTop = el.scrollHeight;
  }, [text]);

  return (
    <div>
      {truncated && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          日志过长，页面只显示最后一部分
        </Typography.Text>
      )}
      <pre
        ref={box}
        className="zf-log"
        onScroll={(e) => {
          const el = e.currentTarget;
          follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
      >
        {text || (task.status === "queued" ? "排队中，尚未开始…" : "（暂无输出）")}
      </pre>
    </div>
  );
}

function ParamsView({ task }: { task: Task }) {
  const p = task.params as Record<string, unknown>;
  const show = (v: unknown) =>
    Array.isArray(v) ? v.join(", ") : v === null || v === undefined || v === "" ? "-" : String(v);
  const entries = Object.entries(p).filter(([k]) => k !== "factors");
  const factors = Array.isArray(p.factors) ? (p.factors as string[]) : null;
  return (
    <Space direction="vertical" size={8} style={{ width: "100%" }}>
      {factors && (
        <div>
          <Typography.Text type="secondary">因子（{factors.length}）：</Typography.Text>
          <div style={{ maxHeight: 120, overflow: "auto" }}>
            {factors.map((f) => (
              <Tag key={f} style={{ marginBottom: 4 }}>
                <Link to={factorHref(f)}>{f}</Link>
              </Tag>
            ))}
          </div>
        </div>
      )}
      <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 3 }}>
        {entries.map(([k, v]) => (
          <Descriptions.Item key={k} label={k}>
            {show(v)}
          </Descriptions.Item>
        ))}
      </Descriptions>
    </Space>
  );
}

function TaskDetail({ id }: { id: string }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const task = useQuery({
    queryKey: ["tasks", "one", id],
    queryFn: () => fetchTask(id),
    refetchInterval: (q) => (q.state.data && !isActive(q.state.data.status) ? false : LIST_POLL_MS),
    staleTime: 0,
  });
  const cancel = useMutation({
    mutationFn: () => cancelTask(id),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["tasks"] });
      message.info("已发送取消");
    },
    onError: (e: Error) => message.error(e.message),
  });
  const retry = useMutation({
    mutationFn: () => retryTask(id),
    onSuccess: (t) => {
      client.invalidateQueries({ queryKey: ["tasks"] });
      navigate(`/tasks/${t.id}`);
    },
    onError: (e: Error) => message.error(e.message),
  });

  if (task.error) return <ErrorState error={task.error} title="任务加载失败" onRetry={() => task.refetch()} />;
  const t = task.data;
  if (!t) return <Card loading />;
  const firstFactor = Array.isArray(t.params.factors) ? (t.params.factors as string[])[0] : undefined;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card size="small">
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <Typography.Title level={5} style={{ margin: 0, flex: 1, minWidth: 200 }}>
              {t.title}
            </Typography.Title>
            <Space wrap>
              {isActive(t.status) && (
                <Button
                  danger
                  loading={cancel.isPending}
                  onClick={() =>
                    Modal.confirm({
                      title: "取消这个任务？",
                      content:
                        t.kind === "evaluate"
                          ? "正在写入的评估结果会被标记为已取消，看板不会显示它。"
                          : "任务进程会被终止，已经写出的部分数据会保留。",
                      okText: "取消任务",
                      okButtonProps: { danger: true },
                      cancelText: "不取消",
                      onOk: () => cancel.mutate(),
                    })
                  }
                >
                  取消
                </Button>
              )}
              {!isActive(t.status) && (
                <Button loading={retry.isPending} onClick={() => retry.mutate()}>
                  用相同参数重跑
                </Button>
              )}
              {t.kind === "evaluate" && t.status === "succeeded" && firstFactor && t.run_id && (
                <Link to={factorHref(firstFactor, { run: t.run_id })}>
                  <Button type="primary">查看结果</Button>
                </Link>
              )}
            </Space>
          </div>
          <TaskProgress task={t} size="default" />
          <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }}>
            <Descriptions.Item label="类型">{KIND_LABEL[t.kind as TaskKind] ?? t.kind}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={STATUS_COLOR[t.status]}>{STATUS_LABEL[t.status]}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="创建">{fmtTime(t.created_at)}</Descriptions.Item>
            <Descriptions.Item label="耗时">{duration(t.started_at, t.finished_at)}</Descriptions.Item>
            {t.run_id && <Descriptions.Item label="run">{t.run_id}</Descriptions.Item>}
            {t.parent_id && (
              <Descriptions.Item label="来自">
                <Link to={`/tasks/${t.parent_id}`}>{t.parent_id}</Link>
              </Descriptions.Item>
            )}
            <Descriptions.Item label="来源">{t.source}</Descriptions.Item>
            {t.exit_code !== null && <Descriptions.Item label="退出码">{t.exit_code}</Descriptions.Item>}
          </Descriptions>
          {t.error && t.status !== "succeeded" && (
            <Alert
              type="error"
              showIcon
              message="错误"
              description={<pre className="zf-log zf-log-short">{t.error}</pre>}
            />
          )}
        </Space>
      </Card>
      <Card size="small" title="参数">
        <ParamsView task={t} />
        <Typography.Paragraph
          type="secondary"
          copyable={{ text: t.command.join(" ") }}
          style={{ fontSize: 12, marginTop: 8, marginBottom: 0, wordBreak: "break-all" }}
        >
          {t.command.slice(3).join(" ")}
        </Typography.Paragraph>
      </Card>
      <Card size="small" title="日志">
        <TaskLog task={t} />
      </Card>
    </Space>
  );
}

export default function Tasks() {
  const id = useParams().id;
  const navigate = useNavigate();
  const screens = Grid.useBreakpoint();
  const wide = screens.lg !== false;
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [kind, setKind] = useState<TaskKind | "">("");
  const tasks = useQuery({
    queryKey: ["tasks", "list", statusFilter, kind],
    queryFn: () => fetchTasks({ status: STATUS_FILTERS[statusFilter], kind: kind || undefined, limit: 200 }),
    refetchInterval: LIST_POLL_MS,
    staleTime: 0,
  });

  const list = (
    <Card
      size="small"
      title="任务"
      extra={
        <Select<TaskKind | "">
          size="small"
          value={kind}
          onChange={setKind}
          style={{ width: 110 }}
          options={[
            { value: "", label: "全部类型" },
            ...(Object.keys(KIND_LABEL) as TaskKind[]).map((k) => ({ value: k, label: KIND_LABEL[k] })),
          ]}
        />
      }
    >
      <Segmented<StatusFilter>
        size="small"
        block
        value={statusFilter}
        onChange={setStatusFilter}
        options={[
          { value: "all", label: "全部" },
          { value: "active", label: `进行中${tasks.data ? ` ${tasks.data.running + tasks.data.queued}` : ""}` },
          { value: "done", label: "成功" },
          { value: "failed", label: "失败/取消" },
        ]}
        style={{ marginBottom: 8 }}
      />
      {tasks.error ? (
        <ErrorState error={tasks.error} title="任务列表加载失败" onRetry={() => tasks.refetch()} />
      ) : (
        <List<Task>
          size="small"
          loading={tasks.isLoading}
          dataSource={tasks.data?.tasks ?? []}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有任务" /> }}
          style={{ maxHeight: wide ? "calc(100vh - 230px)" : undefined, overflow: "auto" }}
          renderItem={(t) => (
            <List.Item
              className={`zf-task-item${t.id === id ? " zf-task-item-active" : ""}`}
              onClick={() => navigate(`/tasks/${t.id}`)}
            >
              <div style={{ width: "100%", minWidth: 0 }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Typography.Text ellipsis style={{ flex: 1, minWidth: 0 }} title={t.title}>
                    {t.title}
                  </Typography.Text>
                  <Tag color={STATUS_COLOR[t.status]} style={{ marginInlineEnd: 0 }}>
                    {t.status === "running" && t.progress_total
                      ? `${t.progress_done}/${t.progress_total}`
                      : STATUS_LABEL[t.status]}
                  </Tag>
                </div>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {KIND_LABEL[t.kind as TaskKind] ?? t.kind} · {fmtTime(t.created_at)}
                  {t.source !== "web" ? ` · ${t.source}` : ""}
                </Typography.Text>
              </div>
            </List.Item>
          )}
        />
      )}
    </Card>
  );

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        message="这里列出工作台发起的任务。在命令行直接运行的评估或构建不会出现在此列表中，也不计入并发上限。"
      />
      <div className="zf-tasks-layout">
        {(wide || !id) && <div className="zf-tasks-list">{list}</div>}
        {id ? (
          <div className="zf-tasks-detail">
            {!wide && (
              <Button type="link" onClick={() => navigate("/tasks")} style={{ padding: 0, marginBottom: 8 }}>
                ← 任务列表
              </Button>
            )}
            <TaskDetail id={id} />
          </div>
        ) : (
          wide && (
            <Card size="small" className="zf-tasks-detail">
              <Empty description="选择左侧的任务查看参数和日志" />
            </Card>
          )
        )}
      </div>
    </Space>
  );
}
