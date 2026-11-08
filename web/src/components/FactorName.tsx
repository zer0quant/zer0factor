import { Tag, Tooltip, Typography } from "antd";
import { Link } from "react-router-dom";
import { baseLabel, factorHref, parseFactorName, prepColor, prepLabel } from "../factorName";

/**
 * A factor name as segments: coloured preprocessing tag, base factor, window.
 * The full systematic name is in the tooltip and can be copied.
 */
export function FactorChips({
  name,
  link = true,
  copyable = false,
}: {
  name: string;
  link?: boolean;
  copyable?: boolean;
}) {
  const p = parseFactorName(name);
  const body = (
    <span className="zf-chips-text">
      <span className="zf-chips-base">{baseLabel(p.base)}</span>
      {p.window != null && <span className="zf-chips-win num">MA{p.window}</span>}
    </span>
  );
  return (
    <span className="zf-chips">
      <Tag color={prepColor(p.prep)} bordered={false}>
        {prepLabel(p.prep)}
      </Tag>
      <Tooltip title={name} mouseEnterDelay={0.4}>
        {link ? (
          <Link to={factorHref(name)} aria-label={name}>
            {body}
          </Link>
        ) : (
          body
        )}
      </Tooltip>
      {copyable && (
        <Typography.Text
          className="zf-chips-copy"
          copyable={{ text: name, tooltips: ["复制完整因子名", "已复制"] }}
        />
      )}
    </span>
  );
}
