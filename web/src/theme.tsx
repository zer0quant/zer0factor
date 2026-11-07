import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { ConfigProvider, theme as antdTheme } from "antd";
import zhCN from "antd/locale/zh_CN";

export type ThemeMode = "system" | "light" | "dark";

const STORAGE_KEY = "zer0factor.theme";

/** Concrete colours for canvas charts (ECharts cannot read CSS variables). */
export interface Palette {
  dark: boolean;
  up: string;
  down: string;
  ink: string;
  muted: string;
  surface: string;
  border: string;
}

const LIGHT: Palette = {
  dark: false,
  up: "#cf1322",
  down: "#389e0d",
  ink: "#111827",
  muted: "#9ca3af",
  surface: "#f8fafc",
  border: "#111827",
};

const DARK: Palette = {
  dark: true,
  up: "#f5544a",
  down: "#49aa19",
  ink: "#e5e7eb",
  muted: "#6b7280",
  surface: "#1f1f1f",
  border: "#f5f5f5",
};

interface ThemeState {
  mode: ThemeMode;
  setMode: (m: ThemeMode) => void;
  palette: Palette;
}

const ThemeContext = createContext<ThemeState>({ mode: "system", setMode: () => {}, palette: LIGHT });

function readStored(): ThemeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

function systemDark(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readStored);
  const [sysDark, setSysDark] = useState(systemDark);

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const on = (e: MediaQueryListEvent) => setSysDark(e.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  const dark = mode === "dark" || (mode === "system" && sysDark);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
  }, [dark]);

  const setMode = (m: ThemeMode) => {
    setModeState(m);
    try {
      if (m === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, m);
    } catch {
      /* storage unavailable: keep the in-memory choice */
    }
  };

  const value = useMemo(() => ({ mode, setMode, palette: dark ? DARK : LIGHT }), [mode, dark]);

  return (
    <ThemeContext.Provider value={value}>
      <ConfigProvider
        locale={zhCN}
        theme={{
          algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
          token: { borderRadius: 8 },
        }}
      >
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeContext);
export const usePalette = () => useContext(ThemeContext).palette;
