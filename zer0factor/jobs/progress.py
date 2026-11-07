"""Derive task progress from CLI log lines."""

from __future__ import annotations


class Progress:
    def __init__(self, kind: str, total: int | None) -> None:
        self.kind = kind
        self.total = total
        self.done = 0
        self.last_line: str | None = None

    def feed(self, line: str) -> bool:
        line = line.rstrip()
        if not line:
            return False
        self.last_line = line[-500:]
        if self.kind == "evaluate" and "evaluation_factor_finished" in line:
            self.done += 1
        elif self.kind == "warm" and (line.startswith("ok ") or line.startswith("fail ")):
            self.done += 1
        return True
