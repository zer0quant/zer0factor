import { useState } from "react";
import { Modal } from "antd";
import { SHORTCUTS, useHotkeys } from "./hotkeys";
import {
  Button,
  Drawer,
  Grid,
  Layout,
  Menu,
  Popover,
  Result,
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
import { periodLabel, returnTypeLabel } from "./vocab";
import { UniverseTag } from "./components/UniverseTag";
import { useTheme } from "./theme";
import type { Meta } from "./types";
import Board from "./pages/Board";
import FactorDetail from "./pages/FactorDetail";
import BaseHome from "./pages/BaseHome";
import Compare from "./pages/Compare";
import Tasks from "./pages/Tasks";
import Families from "./pages/Families";
import { TaskBadge } from "./components/TaskBadge";
import { EvaluateProvider } from "./components/EvaluateDrawer";

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
      <UniverseTag code={std.universe} />
      <Tag>{fmtDate(std.start_date)} 至今</Tag>
      <Tag>{std.quantiles} 分位</Tag>
      <Tag>持有 {periodLabel(std.period)}</Tag>
      <Tag>{returnTypeLabel(std.return_type)}</Tag>
    </Space>
  );
}

const ICON = {
  width: 16,
  height: 16,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

const MoonIcon = () => (
  <svg {...ICON}>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </svg>
);

const SunIcon = () => (
  <svg {...ICON}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </svg>
);

/** One icon button: shows where a click takes you (moon → dark, sun → light). */
function ThemeSwitch({ withText = false }: { withText?: boolean }) {
  const { dark, toggle } = useTheme();
  const hint = dark ? "切换到浅色" : "切换到深色";
  const button = (
    <Button
      size="small"
      type="text"
      aria-label={hint}
      icon={dark ? <SunIcon /> : <MoonIcon />}
      onClick={toggle}
      style={{ display: "inline-flex", alignItems: "center", justifyContent: "center" }}
    >
      {withText ? hint : null}
    </Button>
  );
  return withText ? button : <Tooltip title={hint}>{button}</Tooltip>;
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
  const [helpOpen, setHelpOpen] = useState(false);
  useHotkeys({ "?": () => setHelpOpen((o) => !o) });
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

  const path = location.pathname;
  const selected = path.startsWith("/compare")
    ? "compare"
    : path.startsWith("/families")
      ? "families"
      : path.startsWith("/tasks")
        ? "tasks"
        : path.startsWith("/factor") || path.startsWith("/base")
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
        { key: "families", label: <Link to="/families">因子族</Link> },
        { key: "tasks", label: <Link to="/tasks">任务</Link> },
      ]}
    />
  );

  return (
    <EvaluateProvider>
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
              <div style={{ padding: "16px 12px" }}>
                <ThemeSwitch withText />
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
                  <Space size={4}>
                    <Tooltip title="看板指标统一取自满足此口径的最新一次评估">
                      <Typography.Text type="secondary">统一评估口径</Typography.Text>
                    </Tooltip>
                    <StandardTags std={std} />
                  </Space>
                ) : (
                  <Popover
                    trigger="click"
                    title="统一评估口径"
                    content={
                      <Space direction="vertical" size={8} style={{ maxWidth: 260 }}>
                        <StandardTags std={std} />
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          看板指标统一取自满足此口径的最新一次评估
                          {meta.data && `；扫描于 ${meta.data.scanned_at.replace("T", " ")}`}
                        </Typography.Text>
                      </Space>
                    }
                  >
                    <Button size="small">评估口径</Button>
                  </Popover>
                ))}
              {meta.data && screens.xl && (
                <Typography.Text type="secondary">扫描于 {meta.data.scanned_at.replace("T", " ")}</Typography.Text>
              )}
              <TaskBadge />
              {!compact && (
                <Tooltip title="键盘快捷键（?）">
                  <Button size="small" type="text" aria-label="键盘快捷键" onClick={() => setHelpOpen(true)}>
                    ?
                  </Button>
                </Tooltip>
              )}
              {!compact && <ThemeSwitch />}
              <Button size="small" loading={doRefresh.isPending} onClick={() => doRefresh.mutate()}>
                {compact ? "刷新" : "刷新数据"}
              </Button>
            </Space>
          </Header>
          <Modal title="键盘快捷键" open={helpOpen} onCancel={() => setHelpOpen(false)} footer={null} width={420}>
            {SHORTCUTS.map(([group, items]) => (
              <div key={group} style={{ marginBottom: 12 }}>
                <Typography.Text strong>{group}</Typography.Text>
                {items.map(([k, desc]) => (
                  <div key={k} className="zf-metric-row">
                    <Typography.Text type="secondary">{desc}</Typography.Text>
                    <span>
                      {k.split(" ").map((part, i) =>
                        (part === "/" && k !== "/") || part === "或" ? (
                          <span key={i} style={{ marginInline: 4 }}>
                            {part === "或" ? "或" : "/"}
                          </span>
                        ) : (
                          <kbd key={i} className="zf-kbd">
                            {part}
                          </kbd>
                        ),
                      )}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </Modal>
          <Content style={{ padding: compact ? 12 : 24, minWidth: 0 }}>
            <Routes>
              <Route path="/" element={<Board />} />
              <Route path="/base/:base" element={<BaseHome />} />
              <Route path="/factor/:name" element={<FactorDetail />} />
              <Route path="/compare" element={<Compare />} />
              <Route path="/families" element={<Families />} />
              <Route path="/tasks" element={<Tasks />} />
              <Route path="/tasks/:id" element={<Tasks />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Content>
        </Layout>
      </Layout>
    </EvaluateProvider>
  );
}
