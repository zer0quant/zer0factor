/** Remembers the board's URL query so links back to it restore filters, sort and view. */
const KEY = "zer0factor.board.search";

export function rememberBoardSearch(search: string) {
  try {
    sessionStorage.setItem(KEY, search);
  } catch {
    /* storage unavailable: links fall back to the plain board */
  }
}

export function boardHref(): string {
  try {
    const s = sessionStorage.getItem(KEY);
    return s ? `/?${s}` : "/";
  } catch {
    return "/";
  }
}
