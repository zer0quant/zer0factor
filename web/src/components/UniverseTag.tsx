import { Tag, Tooltip } from "antd";
import { universeLabel, universeRules } from "../vocab";

function Definition({ code }: { code: string }) {
  const rules = universeRules(code);
  return (
    <div style={{ maxWidth: 300, fontSize: 12, lineHeight: 1.6 }}>
      {rules?.map(([heading, items], i) => (
        <div key={i} style={{ marginBottom: 4 }}>
          {heading && <div>{heading}</div>}
          {items.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {items.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          )}
        </div>
      ))}
      <div style={{ opacity: 0.7 }}>
        代号 <code>{code}</code>
      </div>
    </div>
  );
}

/** Universe shown by its Chinese name, with a "?" whose tooltip gives the filter rules and code. */
export function UniverseTag({ code, plain = false }: { code: string | null | undefined; plain?: boolean }) {
  const label = universeLabel(code);
  if (!code) return plain ? <>{label}</> : <Tag>{label}</Tag>;
  const mark = (
    <Tooltip title={<Definition code={code} />}>
      <span
        aria-label={`${label}的定义`}
        role="img"
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 14,
          height: 14,
          marginLeft: 4,
          borderRadius: "50%",
          border: "1px solid currentColor",
          fontSize: 10,
          lineHeight: 1,
          cursor: "help",
          opacity: 0.65,
          verticalAlign: "middle",
        }}
      >
        ?
      </span>
    </Tooltip>
  );
  return plain ? (
    <span>
      {label}
      {mark}
    </span>
  ) : (
    <Tag>
      {label}
      {mark}
    </Tag>
  );
}

