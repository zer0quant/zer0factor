import { useSyncExternalStore } from "react";

/**
 * The compare basket: factors picked on the board, the matrix or a detail page.
 * Kept in localStorage so it survives navigation and reloads, and synced across tabs.
 */
export const MAX_COMPARE = 8;
const KEY = "zer0factor.compare";

function read(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string").slice(0, MAX_COMPARE) : [];
  } catch {
    return [];
  }
}

let current = read();
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key === KEY) {
      current = read();
      emit();
    }
  });
}

export function setBasket(names: string[]) {
  current = [...new Set(names)].slice(0, MAX_COMPARE);
  try {
    if (current.length) localStorage.setItem(KEY, JSON.stringify(current));
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: keep the in-memory basket */
  }
  emit();
}

/** Add or remove one factor; returns false when adding would exceed the limit. */
export function toggleInBasket(name: string): boolean {
  if (current.includes(name)) {
    setBasket(current.filter((n) => n !== name));
    return true;
  }
  if (current.length >= MAX_COMPARE) return false;
  setBasket([...current, name]);
  return true;
}

export function useBasket(): string[] {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => current,
  );
}

export const compareHref = (names: string[]) => `/compare?f=${encodeURIComponent(names.join(","))}`;
