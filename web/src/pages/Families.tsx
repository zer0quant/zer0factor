import { useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { createTask, fetchFamilies, patchFamily } from "../api";
import { useEvaluate } from "../components/EvaluateDrawer";
import { ErrorState } from "../components/states";
import { STATUS_COLOR, STATUS_LABEL, fmtTime } from "../taskStatus";
import { fmtDate } from "../format";
import type { Family } from "../types";

interface BuildValues {
  stage: "raw" | "preprocess" | "all";
  start_date?: string;
  end_date?: string;
  workers: number;
  update_registry: boolean;
}

const STAGES = [
  { value: "raw", label: "原始计算" },
  { value: "preprocess", label: "预处理" },
  { value: "all", label: "全部" },
];
const DATE_RULE = { pattern: /^\d{8}$/, message: "日期格式为 YYYYMMDD" };

function BuildModal({ family, onClose }: { family: Family | null; onClose: () => void }) {
  const [form] = Form.useForm<BuildValues>();
  const navigate = useNavigate();
  const client = useQueryClient();
  const submit = useMutation({
    mutationFn: (v: BuildValues) =>
      createTask("build", {
        family: family!.name,
        stage: v.stage,
        start_date: v.start_date || null,
        end_date: v.end_date || null,
        workers: v.workers,
        update_registry: v.update_registry,
      }),
    onSuccess: (t) => {
      client.invalidateQueries({ queryKey: ["tasks"] });
      client.invalidateQueries({ queryKey: ["families"] });
      onClose();
      navigate(`/tasks/${t.id}`);
    },
    onError: (e: Error) => message.error(e.message),
  });
  const onOk = async () => {
    const v = await form.validateFields();
    if (v.stage === "all") {
      Modal.confirm({
        title: `构建 ${family!.name} 的全部阶段？`,
        content: `将重新计算 ${family!.raw_names.length} 个原始因子并生成 ${family!.outputs.length} 个输出因子，覆盖 data/factors 下的同名数据，可能耗时较长。`,
        okText: "开始构建",
        cancelText: "再想想",
        onOk: () => submit.mutate(v),
      });
    } else {
      submit.mutate(v);
    }
  };
  return (
    <Modal
      title={family ? `构建 ${family.name}` : ""}
      open={!!family}
      onCancel={onClose}
      onOk={onOk}
      okText="提交构建"
      confirmLoading={submit.isPending}
      destroyOnClose
    >
      <Form<BuildValues>
        form={form}
        layout="vertical"
        preserve={false}
        initialValues={{ stage: "all", workers: 8, update_registry: false }}
      >
        <Form.Item name="stage" label="阶段">
          <Radio.Group options={STAGES} optionType="button" />
        </Form.Item>
        <Space wrap>
          <Form.Item name="start_date" label="起始日" rules={[DATE_RULE]} extra="留空 = 配置默认">
            <Input placeholder="YYYYMMDD" style={{ width: 130 }} allowClear />
          </Form.Item>
          <Form.Item name="end_date" label="结束日" rules={[DATE_RULE]} extra="留空 = 最新">
            <Input placeholder="最新" style={{ width: 130 }} allowClear />
          </Form.Item>
          <Form.Item name="workers" label="workers">
            <InputNumber min={1} max={64} style={{ width: 90 }} />
          </Form.Item>
        </Space>
        <Form.Item name="update_registry" valuePropName="checked">
          <Checkbox>把输出因子登记进 config/factors.toml</Checkbox>
        </Form.Item>
      </Form>
    </Modal>
  );
}

function NoteModal({ family, onClose }: { family: Family | null; onClose: () => void }) {
  const [note, setNote] = useState("");
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: () => patchFamily(family!.name, { note }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["families"] });
      onClose();
    },
    onError: (e: Error) => message.error(e.message),
  });
  return (
    <Modal
      title={family ? `备注：${family.name}` : ""}
      open={!!family}
      onCancel={onClose}
      onOk={() => save.mutate()}
      confirmLoading={save.isPending}
      afterOpenChange={(open) => open && setNote(family?.note ?? "")}
      okText="保存"
    >
      <Input.TextArea rows={4} value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} />
    </Modal>
  );
}

function BaseFactors() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const run = useMutation({
    mutationFn: (target: "returns" | "market_cap") => createTask("base", { target }),
    onSuccess: (t) => {
      client.invalidateQueries({ queryKey: ["tasks"] });
      navigate(`/tasks/${t.id}`);
    },
    onError: (e: Error) => message.error(e.message),
  });
  const confirm = (target: "returns" | "market_cap", label: string) =>
    Modal.confirm({
      title: `重新计算${label}？`,
      content: "会从 zer0share 读取全部股票的行情并覆盖 data/factors 下的同名因子。",
      okText: "开始计算",
      cancelText: "再想想",
      onOk: () => run.mutate(target),
    });
  return (
    <Card size="small" title="基础因子">
      <Space wrap>
        <Typography.Text type="secondary">daily_return / open_return 等收益因子是 rolling_return 族的输入。</Typography.Text>
        <Button onClick={() => confirm("returns", "基础收益因子")}>计算收益因子</Button>
        <Button onClick={() => confirm("market_cap", "市值因子")}>计算市值因子</Button>
      </Space>
    </Card>
  );
}

export default function Families() {
  const client = useQueryClient();
  const evaluate = useEvaluate();
  const [showArchived, setShowArchived] = useState(false);
  const [query, setQuery] = useState("");
  const [building, setBuilding] = useState<Family | null>(null);
  const [noting, setNoting] = useState<Family | null>(null);
  const families = useQuery({ queryKey: ["families"], queryFn: () => fetchFamilies() });
  const rescan = useMutation({
    mutationFn: () => fetchFamilies(true),
    onSuccess: (data) => {
      client.setQueryData(["families"], data);
      message.success(`已重新扫描，共 ${data.families.length} 个因子族`);
    },
    onError: (e: Error) => message.error(e.message),
  });
  const setStatus = useMutation({
    mutationFn: ({ name, status }: { name: string; status: "enabled" | "archived" }) =>
      patchFamily(name, { status }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["families"] }),
    onError: (e: Error) => message.error(e.message),
  });

  const all = families.data?.families ?? [];
  const broken = all.filter((f) => f.error);
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return all
      .filter((f) => !f.error)
      .filter((f) => showArchived || f.status !== "archived")
      .filter((f) => !q || f.name.toLowerCase().includes(q) || f.module.toLowerCase().includes(q));
  }, [all, showArchived, query]);
  const nArchived = all.filter((f) => !f.error && f.status === "archived").length;

  const columns: ColumnsType<Family> = [
    {
      title: "因子族",
      dataIndex: "name",
      render: (_, f) => (
        <Space direction="vertical" size={0}>
          <Space size={4} wrap>
            <Typography.Text strong>{f.name}</Typography.Text>
            {f.is_new && <Tag color="green">新</Tag>}
            {f.status === "archived" && <Tag>已归档</Tag>}
            {f.source && (
              <Tooltip
                title={Object.entries(f.source).map(([k, v]) => (
                  <div key={k}>
                    {k}: {String(v)}
                  </div>
                ))}
              >
                <Tag color="purple">来源</Tag>
              </Tooltip>
            )}
          </Space>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {f.module}
          </Typography.Text>
          {f.note && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }} ellipsis={{ tooltip: f.note }}>
              备注：{f.note}
            </Typography.Text>
          )}
        </Space>
      ),
    },
    {
      title: "已算 / 输出",
      key: "stored",
      width: 120,
      sorter: (a, b) => a.stored / Math.max(1, a.outputs.length) - b.stored / Math.max(1, b.outputs.length),
      render: (_, f) => (
        <Typography.Text type={f.stored === 0 ? "secondary" : undefined}>
          {f.stored} / {f.outputs.length}
        </Typography.Text>
      ),
    },
    {
      title: "数据截至",
      dataIndex: "data_end",
      width: 110,
      sorter: (a, b) => (a.data_end ?? "").localeCompare(b.data_end ?? ""),
      render: (v: string | null) => (v ? fmtDate(v) : <Typography.Text type="secondary">未计算</Typography.Text>),
    },
    {
      title: "最近构建",
      key: "last_task",
      width: 150,
      render: (_, f) =>
        f.last_task ? (
          <Link to={`/tasks/${f.last_task.id}`}>
            <Tag color={STATUS_COLOR[f.last_task.status]}>{STATUS_LABEL[f.last_task.status]}</Tag>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {fmtTime(f.last_task.created_at)}
            </Typography.Text>
          </Link>
        ) : (
          <Typography.Text type="secondary">-</Typography.Text>
        ),
    },
    {
      title: "操作",
      key: "actions",
      width: 260,
      render: (_, f) => (
        <Space size={4} wrap>
          <Button size="small" type="primary" ghost onClick={() => setBuilding(f)}>
            构建
          </Button>
          <Tooltip title={f.stored ? `用已算好的 ${f.stored} 个因子新建评估` : "还没有已算好的因子"}>
            <Button size="small" disabled={!f.stored} onClick={() => evaluate.open(f.stored_names)}>
              接着评估
            </Button>
          </Tooltip>
          <Button size="small" type="text" onClick={() => setNoting(f)}>
            备注
          </Button>
          <Button
            size="small"
            type="text"
            onClick={() =>
              setStatus.mutate({ name: f.name, status: f.status === "archived" ? "enabled" : "archived" })
            }
          >
            {f.status === "archived" ? "恢复" : "归档"}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <BaseFactors />
      {broken.length > 0 && (
        <Alert
          type="error"
          showIcon
          message={`${broken.length} 个因子族加载失败`}
          description={
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              {broken.map((f) => (
                <div key={`${f.module}:${f.name}`}>
                  <Typography.Text strong>{f.name}</Typography.Text>{" "}
                  <Typography.Text type="secondary">({f.module})</Typography.Text>
                  <pre className="zf-log zf-log-short">{f.error}</pre>
                </div>
              ))}
            </Space>
          }
        />
      )}
      <Card
        size="small"
        title={`因子族${families.data ? `（${rows.length}）` : ""}`}
        extra={
          <Space wrap>
            <Input.Search
              size="small"
              allowClear
              placeholder="搜索族名或模块"
              onChange={(e) => setQuery(e.target.value)}
              style={{ width: 200 }}
            />
            <Space size={4}>
              <Switch size="small" checked={showArchived} onChange={setShowArchived} />
              <Typography.Text type="secondary">显示已归档{nArchived ? `（${nArchived}）` : ""}</Typography.Text>
            </Space>
            {families.data && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                扫描于 {fmtTime(families.data.scanned_at)}
              </Typography.Text>
            )}
            <Button size="small" loading={rescan.isPending} onClick={() => rescan.mutate()}>
              重新扫描
            </Button>
          </Space>
        }
      >
        {families.error ? (
          <ErrorState error={families.error} title="因子族扫描失败" onRetry={() => families.refetch()} />
        ) : (
          <Table<Family>
            size="small"
            rowKey={(f) => `${f.module}:${f.name}`}
            loading={families.isLoading}
            dataSource={rows}
            columns={columns}
            pagination={false}
            scroll={{ x: 800 }}
            expandable={{
              expandedRowRender: (f) => <FamilyOutputs family={f} />,
            }}
          />
        )}
      </Card>
      <BuildModal family={building} onClose={() => setBuilding(null)} />
      <NoteModal family={noting} onClose={() => setNoting(null)} />
    </Space>
  );
}

function FamilyOutputs({ family }: { family: Family }) {
  const stored = new Set(family.stored_names);
  return (
    <Space direction="vertical" size={8} style={{ width: "100%" }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        基础字段 {family.base_factors.join(", ") || "-"} · 窗口 {family.windows.join(", ") || "-"} · 预处理{" "}
        {family.profiles.join(", ")}
        {family.uses_data_provider ? " · 从行情数据直接计算" : " · 由已存储因子派生"}
      </Typography.Text>
      <div style={{ maxHeight: 260, overflow: "auto" }}>
        {family.outputs.map((n) =>
          stored.has(n) ? (
            <Tag key={n} color="blue" style={{ marginBottom: 4 }}>
              <Link to={`/factor/${encodeURIComponent(n)}`}>{n}</Link>
            </Tag>
          ) : (
            <Tag key={n} style={{ marginBottom: 4, opacity: 0.6 }}>
              {n}
            </Tag>
          ),
        )}
      </div>
    </Space>
  );
}
