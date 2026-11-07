import { useState } from "react";
import {
  Button,
  Drawer,
  Grid,
  Layout,
  Menu,
  Popover,
  Result,
  Segmented,
  Space,
  Tag,
  Tooltip,
  Typography,
  message,
  theme,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { fetchMeta, refresh } from "./api";
import { boardHref } from "./boardState";
import { fmtDate } from "./format";
import { useTheme, type ThemeMode } from "./theme";
import type { Meta } from "./types";
import Board from "./pages/Board";
import FactorDetail from "./pages/FactorDetail";
import Compare from "./pages/Compare";

const { Sider, Header, Content } = Layout;
const HEADER_H = 56;

function Brand() {
  return (
    <div style={{ padding: "20px 20px 12px" }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        zer0factor
      </Typography.Title>
      <Typography.Text type="secondary">因子研究工作台</Typography.Text>
    </div>
  );
}

function StandardTags({ std }: { std: Meta["standard"] }) {
  return (
    <Space size={4} wrap>
      <Tag>{std.universe}</Tag>
      <Tag>{fmtDate(std.start_date)} 起</Tag>
      <Tag>{std.quantiles} 组</Tag>
      <Tag>持有 {std.period}</Tag>
      <Tag>{std.return_type}</Tag>
    </Space>
  );
}

const THEME_OPTIONS: { value: ThemeMode; label: string }[] = [
  { value: "system", label: "自动" },
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
];

function ThemeSwitch() {
  const { mode, setMode } = useTheme();
  return (
    <Tooltip title="配色：跟随系统 / 浅色 / 深色">
      <Segmented<ThemeMode> size="small" options={THEME_OPTIONS} value={mode} onChange={setMode} />
    </Tooltip>
  );
}

function NotFound() {
  return (
    <Result
      status="404"
      title="页面不存在"
      extra={
        <Link to="/">
          <Button type="primary">回到因子看板</Button>
        </Link>
      }
    />
  );
}

export default function App() {
  const location = useLocation();
  const client = useQueryClient();
  const screens = Grid.useBreakpoint();
  const { token } = theme.useToken();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const meta = useQuery({ queryKey: ["meta"], queryFn: fetchMeta });
  const doRefresh = useMutation({
    mutationFn: refresh,
    onSuccess: () => {
      client.invalidateQueries();
      message.success("已重新扫描评估结果");
    },
    onError: (e: Error) => message.error(e.message),
  });

  // Before the first breakpoint measurement `screens.lg` is undefined: treat as wide.
  const wide = screens.lg !== false;
  const compact = screens.md === false;

  const selected = location.pathname.startsWith("/compare")
    ? "compare"
    : location.pathname.startsWith("/factor")
      ? "detail"
      : "board";
  const std = meta.data?.standard;

  const menu = (
    <Menu
      mode="inline"
      selectedKeys={[selected]}
      style={{ borderInlineEnd: "none" }}
      onClick={() => setDrawerOpen(false)}
      items={[
        { key: "board", label: <Link to={boardHref()}>因子看板</Link> },
        { key: "compare", label: <Link to="/compare">因子对比</Link> },
      ]}
    />
  );

  return (
    <Layout style={{ minHeight: "100vh" }}>
      {wide && (
        <Sider
          width={200}
          theme="light"
          style={{
            position: "sticky",
            top: 0,
            height: "100vh",
            overflow: "auto",
            borderInlineEnd: `1px solid ${token.colorSplit}`,
          }}
        >
          <Brand />
          {menu}
        </Sider>
      )}
      {!wide && (
        <Drawer
          placement="left"
          width={220}
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          styles={{ body: { padding: 0 }, header: { display: "none" } }}
        >
          <Brand />
          {menu}
          {compact && (
            <div style={{ padding: "16px 20px" }}>
              <Typography.Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
                配色
              </Typography.Text>
              <ThemeSwitch />
            </div>
          )}
        </Drawer>
      )}
      <Layout style={{ minWidth: 0 }}>
        <Header
          style={{
            position: "sticky",
            top: 0,
            zIndex: 20,
            background: token.colorBgContainer,
            padding: compact ? "0 12px" : "0 24px",
            display: "flex",
            alignItems: "center",
            gap: 12,
            borderBottom: `1px solid ${token.colorSplit}`,
            height: HEADER_H,
            lineHeight: "normal",
          }}
        >
          {!wide && (
            <>
              <Button
                type="text"
                aria-label="打开菜单"
                onClick={() => setDrawerOpen(true)}
                icon={<span style={{ fontSize: 18, lineHeight: 1 }}>☰</span>}
              />
              <Typography.Text strong style={{ fontSize: 16 }}>
                zer0factor
              </Typography.Text>
            </>
          )}
          <div style={{ flex: 1 }} />
          <Space size={compact ? 8 : "middle"}>
            {std &&
              (screens.xl ? (
                <Tooltip title="看板指标统一取自满足此设定、且评估到最新的 run">
                  <Space size={4}>
                    <Typography.Text type="secondary">标准设定</Typography.Text>
                    <StandardTags std={std} />
                  </Space>
                </Tooltip>
              ) : (
                <Popover
                  trigger="click"
                  title="标准设定"
                  content={
                    <Space direction="vertical" size={8} style={{ maxWidth: 260 }}>
                      <StandardTags std={std} />
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        看板指标统一取自满足此设定、且评估到最新的 run
                        {meta.data && `；扫描于 ${meta.data.scanned_at.replace("T", " ")}`}
                      </Typography.Text>
                    </Space>
                  }
                >
                  <Button size="small">标准设定</Button>
                </Popover>
              ))}
            {meta.data && screens.xl && (
              <Typography.Text type="secondary">
                扫描于 {meta.data.scanned_at.replace("T", " ")}
              </Typography.Text>
            )}
            {!compact && <ThemeSwitch />}
            <Button size="small" loading={doRefresh.isPending} onClick={() => doRefresh.mutate()}>
              {compact ? "刷新" : "刷新数据"}
            </Button>
          </Space>
        </Header>
        <Content style={{ padding: compact ? 12 : 24, minWidth: 0 }}>
          <Routes>
            <Route path="/" element={<Board />} />
            <Route path="/factor/:name" element={<FactorDetail />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}
