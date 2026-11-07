import { Button, Popover, Space, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import { compareHref, setBasket, toggleInBasket, useBasket } from "../compareBasket";
import { shortName } from "../factorName";

/** Floating bar showing the compare basket, with a popover listing its factors. */
export function CompareBar() {
  const basket = useBasket();
  const navigate = useNavigate();
  if (!basket.length) return null;
  const list = (
    <Space direction="vertical" size={4} style={{ maxWidth: 360 }}>
      {basket.map((n) => (
        <Space key={n} size={8} style={{ justifyContent: "space-between", width: "100%" }}>
          <span title={n}>{shortName(n)}</span>
          <Button size="small" type="link" onClick={() => toggleInBasket(n)} style={{ padding: 0 }}>
            移除
          </Button>
        </Space>
      ))}
    </Space>
  );
  return (
    <div className="zf-compare-bar" role="region" aria-label="对比篮">
      <Popover content={list} title="对比篮" trigger="click">
        <Typography.Link style={{ color: "inherit", textDecoration: "underline dotted" }}>
          已选 {basket.length} 个{basket.length < 2 ? "（至少 2 个）" : ""}
        </Typography.Link>
      </Popover>
      <Button
        size="small"
        ghost
        style={{ color: "var(--zf-bar-fg)", borderColor: "var(--zf-bar-fg)" }}
        onClick={() => setBasket([])}
      >
        清空
      </Button>
      <Button
        size="small"
        type="primary"
        disabled={basket.length < 2}
        style={{ background: "var(--zf-bar-fg)", color: "var(--zf-bar-bg)" }}
        onClick={() => navigate(compareHref(basket))}
      >
        开始对比
      </Button>
    </div>
  );
}
