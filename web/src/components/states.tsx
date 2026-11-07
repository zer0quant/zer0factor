import { useEffect, useState } from "react";
import { Alert, Button, Space, Spin, Typography } from "antd";

/** Error banner with an optional retry action. */
export function ErrorState({
  error,
  title = "加载失败",
  onRetry,
}: {
  error: unknown;
  title?: string;
  onRetry?: () => void;
}) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <Alert
      type="error"
      showIcon
      message={title}
      description={msg}
      action={
        onRetry && (
          <Button size="small" onClick={onRetry}>
            重试
          </Button>
        )
      }
    />
  );
}

/** Centred spinner with a hint and an elapsed-seconds counter, for slow first-time computations. */
export function SlowLoading({ tip, hint }: { tip: string; hint?: string }) {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div style={{ padding: "48px 16px", textAlign: "center" }}>
      <Space direction="vertical" size={12} align="center">
        <Spin size="large" />
        <Typography.Text>
          {tip}
          {secs >= 2 && <Typography.Text type="secondary">（已等待 {secs} 秒）</Typography.Text>}
        </Typography.Text>
        {hint && (
          <Typography.Text type="secondary" style={{ fontSize: 12, maxWidth: 420, display: "block" }}>
            {hint}
          </Typography.Text>
        )}
      </Space>
    </div>
  );
}
