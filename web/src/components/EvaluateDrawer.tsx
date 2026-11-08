import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { periodLabel, returnTypeLabel, universeLabel } from "../vocab";
import {
  Alert,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Typography,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { createTask, fetchEvalOptions, fetchFactors } from "../api";
import type { EvalOptions, EvaluateParams } from "../types";

type Preset = Partial<Omit<EvaluateParams, "factors">>;

interface Ctx {
  open: (factors: string[], preset?: Preset) => void;
}

const EvaluateContext = createContext<Ctx>({ open: () => undefined });

/** Open the "新建评估" drawer from anywhere: board basket, detail page, families page. */
export const useEvaluate = () => useContext(EvaluateContext);

const BIG_FACTORS = 20;
const BIG_WORKERS = 8;
const DATE_RULE = { pattern: /^\d{8}$/, message: "日期格式为 YYYYMMDD" };

const periodNumber = (p: string) => Number.parseInt(p, 10);

interface FormValues extends Omit<EvaluateParams, "end_date" | "universe" | "benchmark_index"> {
  standard: boolean;
  end_date?: string;
  universe?: string;
  benchmark_index?: string;
}

function standardValues(o: EvalOptions): Partial<FormValues> {
  return {
    start_date: o.standard.start_date,
    quantiles: o.standard.quantiles,
    return_type: o.standard.return_type,
    universe: o.standard.universe,
    end_date: undefined,
  };
}

/** Does a preset (e.g. the parameters of an existing run) satisfy the standard setting? */
function matchesStandard(o: EvalOptions, p: Preset): boolean {
  const std = o.standard;
  return (
    (p.start_date ?? std.start_date) === std.start_date &&
    !p.end_date &&
    (p.quantiles ?? std.quantiles) === std.quantiles &&
    (p.return_type ?? std.return_type) === std.return_type &&
    (p.universe ?? std.universe) === std.universe
  );
}

function EvaluateForm({
  options,
  factors,
  preset,
  onDone,
}: {
  options: EvalOptions;
  factors: string[];
  preset: Preset;
  onDone: () => void;
}) {
  const [form] = Form.useForm<FormValues>();
  const navigate = useNavigate();
  const client = useQueryClient();
  const board = useQuery({ queryKey: ["factors"], queryFn: fetchFactors });
  const standard = Form.useWatch("standard", form) ?? true;
  const stdPeriod = periodNumber(options.standard.period);

  const initial = useMemo<FormValues>(() => {
    const isStd = matchesStandard(options, preset);
    const base = { ...options.defaults, ...preset };
    const periods = base.periods?.length ? base.periods : options.defaults.periods;
    return {
      factors,
      standard: isStd,
      ...base,
      ...(isStd ? standardValues(options) : {}),
      periods: isStd && !periods.includes(stdPeriod) ? [stdPeriod, ...periods] : periods,
      end_date: base.end_date ?? undefined,
      universe: (isStd ? options.standard.universe : base.universe) ?? undefined,
      benchmark_index: base.benchmark_index ?? undefined,
    } as FormValues;
  }, [options, factors, preset, stdPeriod]);

  useEffect(() => form.setFieldsValue(initial), [form, initial]);

  const submit = useMutation({
    mutationFn: (v: FormValues) => {
      const params: EvaluateParams = {
        factors: v.factors,
        start_date: v.start_date,
        end_date: v.end_date || null,
        periods: [...new Set(v.periods.map(Number))].sort((a, b) => a - b),
        quantiles: v.quantiles,
        return_type: v.return_type,
        universe: v.universe || null,
        max_loss: v.max_loss,
        transaction_cost_bps: v.transaction_cost_bps,
        benchmark_index: v.benchmark_index || null,
        workers: v.workers,
      };
      return createTask("evaluate", params as unknown as Record<string, unknown>);
    },
    onSuccess: (task) => {
      client.invalidateQueries({ queryKey: ["tasks"] });
      message.success("已提交评估任务");
      onDone();
      navigate(`/tasks/${task.id}`);
    },
    onError: (e: Error) => message.error(e.message),
  });

  const onFinish = (v: FormValues) => {
    if (v.factors.length > BIG_FACTORS || v.workers > BIG_WORKERS) {
      Modal.confirm({
        title: "确认提交批量评估？",
        content: `将评估 ${v.factors.length} 个因子，workers=${v.workers}。批量评估会占用较多 CPU 和内存，可能持续几十分钟；同一时间只运行一个评估或构建任务，其余排队。`,
        okText: "提交",
        cancelText: "再想想",
        onOk: () => submit.mutate(v),
      });
    } else {
      submit.mutate(v);
    }
  };

  const factorOptions = useMemo(
    () => (board.data ?? []).map((r) => ({ value: r.name, label: r.name })),
    [board.data],
  );
  const nFactors = Form.useWatch("factors", form)?.length ?? 0;

  return (
    <Form<FormValues>
      form={form}
      layout="vertical"
      initialValues={initial}
      onFinish={onFinish}
      onValuesChange={(changed) => {
        if (changed.standard === true) {
          const periods: number[] = form.getFieldValue("periods") ?? [];
          form.setFieldsValue({
            ...standardValues(options),
            periods: periods.includes(stdPeriod) ? periods : [stdPeriod, ...periods],
          });
        }
      }}
      requiredMark={false}
    >
      <Form.Item
        name="factors"
        label={`因子（${nFactors} 个）`}
        rules={[{ required: true, type: "array", min: 1, message: "至少选择 1 个因子" }]}
        extra="可直接粘贴多个因子名，用逗号、空格或换行分隔"
      >
        <Select
          mode="tags"
          tokenSeparators={[",", " ", "\n", "，"]}
          options={factorOptions}
          placeholder="输入或粘贴因子名"
          maxTagCount="responsive"
          allowClear
        />
      </Form.Item>

      <Form.Item name="standard" valuePropName="checked" style={{ marginBottom: 8 }}>
        <Switch checkedChildren="统一口径" unCheckedChildren="自定义" />
      </Form.Item>
      <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
        {standard
          ? `起始日、分组数、成交价、股票池锁定为统一评估口径，结果会进入看板。持有期需包含 ${periodLabel(options.standard.period)}。`
          : "自定义设定的结果不进入看板主表，只在因子详情页的 run 列表里出现，用于稳健性对比。"}
      </Typography.Paragraph>

      <Space wrap size={12} style={{ width: "100%" }}>
        <Form.Item name="start_date" label="起始日" rules={[{ required: true }, DATE_RULE]}>
          <Input disabled={standard} style={{ width: 130 }} placeholder="YYYYMMDD" />
        </Form.Item>
        <Form.Item name="end_date" label="结束日" rules={[DATE_RULE]} extra="留空 = 最新">
          <Input disabled={standard} style={{ width: 130 }} placeholder="最新" allowClear />
        </Form.Item>
        <Form.Item name="quantiles" label="分组数" rules={[{ required: true }]}>
          <InputNumber disabled={standard} min={2} max={50} style={{ width: 90 }} />
        </Form.Item>
      </Space>

      <Form.Item
        name="periods"
        label="持有期（交易日）"
        rules={[
          { required: true, type: "array", min: 1, message: "至少一个持有期" },
          {
            validator: (_, v: number[] = []) =>
              !standard || v.map(Number).includes(stdPeriod)
                ? Promise.resolve()
                : Promise.reject(new Error(`统一口径需包含持有期 ${stdPeriod} 日`)),
          },
        ]}
      >
        <Select
          mode="tags"
          tokenSeparators={[",", " "]}
          options={[1, 5, 10, 20].map((p) => ({ value: p, label: `${p}D` }))}
          onChange={(v: (string | number)[]) =>
            form.setFieldValue(
              "periods",
              v.map(Number).filter((n) => Number.isInteger(n) && n > 0),
            )
          }
        />
      </Form.Item>

      <Space wrap size={12} style={{ width: "100%" }}>
        <Form.Item name="return_type" label="成交价">
          <Select
            disabled={standard}
            style={{ width: 150 }}
            options={options.return_types.map((r) => ({ value: r, label: returnTypeLabel(r) }))}
          />
        </Form.Item>
        <Form.Item name="universe" label="股票池">
          <Select
            disabled={standard}
            allowClear
            placeholder="全部股票"
            style={{ width: 200 }}
            options={options.universes.map((u) => ({ value: u, label: universeLabel(u), title: u }))}
          />
        </Form.Item>
      </Space>

      <Space wrap size={12} style={{ width: "100%" }}>
        <Form.Item name="transaction_cost_bps" label="单边成本 (bps)">
          <InputNumber min={0} max={1000} step={1} style={{ width: 110 }} />
        </Form.Item>
        <Form.Item name="max_loss" label="max_loss">
          <InputNumber min={0} max={1} step={0.05} style={{ width: 100 }} />
        </Form.Item>
        <Form.Item
          name="workers"
          label="workers"
          extra={nFactors > 1 ? "多因子时可调大并行进程数" : undefined}
        >
          <InputNumber min={1} max={64} style={{ width: 90 }} />
        </Form.Item>
      </Space>

      <Form.Item name="benchmark_index" label="基准指数（可选）" extra="如 000300.SH，用于多头指数超额收益">
        <Input style={{ width: 200 }} allowClear />
      </Form.Item>

      <Space>
        <Button type="primary" htmlType="submit" loading={submit.isPending}>
          提交评估
        </Button>
        <Button onClick={onDone}>取消</Button>
      </Space>
    </Form>
  );
}

export function EvaluateProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ factors: string[]; preset: Preset; key: number } | null>(null);
  const options = useQuery({ queryKey: ["eval-options"], queryFn: fetchEvalOptions, enabled: !!state });
  const open = useCallback(
    (factors: string[], preset: Preset = {}) =>
      setState({ factors: [...new Set(factors)], preset, key: Date.now() }),
    [],
  );
  const close = () => setState(null);
  return (
    <EvaluateContext.Provider value={{ open }}>
      {children}
      <Drawer title="新建评估" width={520} open={!!state} onClose={close} destroyOnClose>
        {options.error ? (
          <Alert type="error" showIcon message="评估参数加载失败" description={String(options.error)} />
        ) : options.data && state ? (
          <EvaluateForm
            key={state.key}
            options={options.data}
            factors={state.factors}
            preset={state.preset}
            onDone={close}
          />
        ) : null}
      </Drawer>
    </EvaluateContext.Provider>
  );
}
