import { Button, Layout, Menu, Space, Tag, Tooltip, Typography, message } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { fetchMeta, refresh } from "./api";
import { fmtDate } from "./format";
import Board from "./pages/Board";
import FactorDetail from "./pages/FactorDetail";
import Compare from "./pages/Compare";

const { Sider, Header, Content } = Layout;

export default function App() {
  const location = useLocation();
  const client = useQueryClient();
  const meta = useQuery({ queryKey: ["meta"], queryFn: fetchMeta });
  const doRefresh = useMutation({
    mutationFn: refresh,
    onSuccess: () => {
      client.invalidateQueries();
      message.success("已重新扫描评估结果");
    },
    onError: (e: Error) => message.error(e.message),
  });

  const selected = location.pathname.startsWith("/compare")
    ? "compare"
    : location.pathname.startsWith("/factor")
      ? "detail"
      : "board";
  const std = meta.data?.standard;

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider width={200} theme="light" breakpoint="lg" collapsedWidth={0}>
        <div style={{ padding: "20px 20px 12px" }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            zer0factor
          </Typography.Title>
          <Typography.Text type="secondary">因子研究工作台</Typography.Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selected]}
          items={[
            { key: "board", label: <Link to="/">因子看板</Link> },
            { key: "compare", label: <Link to="/compare">因子对比</Link> },
          ]}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: "#fff",
            padding: "0 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
            borderBottom: "1px solid #f0f0f0",
            height: 56,
          }}
        >
          <Space size="middle" wrap>
            {std && (
              <Tooltip title="看板指标统一取自满足此设定、且评估到最新的 run">
                <Space size={4}>
                  <Typography.Text type="secondary">标准设定</Typography.Text>
                  <Tag>{std.universe}</Tag>
                  <Tag>{fmtDate(std.start_date)} 起</Tag>
                  <Tag>{std.quantiles} 组</Tag>
                  <Tag>持有 {std.period}</Tag>
                  <Tag>{std.return_type}</Tag>
                </Space>
              </Tooltip>
            )}
            {meta.data && (
              <Typography.Text type="secondary">
                扫描于 {meta.data.scanned_at.replace("T", " ")}
              </Typography.Text>
            )}
            <Button size="small" loading={doRefresh.isPending} onClick={() => doRefresh.mutate()}>
              刷新数据
            </Button>
          </Space>
        </Header>
        <Content style={{ padding: 24, background: "#f5f6f8" }}>
          <Routes>
            <Route path="/" element={<Board />} />
            <Route path="/factor/:name" element={<FactorDetail />} />
            <Route path="/compare" element={<Compare />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}
