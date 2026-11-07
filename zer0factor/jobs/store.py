"""SQLite-backed task and factor-family state for the workbench.

The store is shared between the web server (scheduler thread, API handlers) and detached
runner processes, so every call opens its own short-lived connection in WAL mode.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

TERMINAL = frozenset({"succeeded", "failed", "cancelled", "lost"})
ACTIVE = frozenset({"queued", "running"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    queue TEXT NOT NULL,
    title TEXT NOT NULL,
    params TEXT NOT NULL,
    command TEXT NOT NULL,
    cwd TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    pid INTEGER,
    exit_code INTEGER,
    progress_done INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER,
    last_line TEXT,
    run_id TEXT,
    parent_id TEXT,
    error TEXT,
    source TEXT NOT NULL DEFAULT 'web',
    seq INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS tasks_status ON tasks(status, queue, seq);
CREATE TABLE IF NOT EXISTS families (
    name TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'enabled',
    note TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_task_id() -> str:
    return f"t_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(2)}"


class TaskStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir = self.db_path.parent / "logs"
        self.log_dir.mkdir(exist_ok=True)
        with self._conn() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        con = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            yield con
        finally:
            con.close()

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        task = dict(row)
        task.pop("seq", None)
        task["params"] = json.loads(task["params"])
        task["command"] = json.loads(task["command"])
        return task

    # ---- tasks -------------------------------------------------------------------------

    def create(
        self,
        *,
        kind: str,
        queue: str,
        title: str,
        params: dict,
        command: list[str],
        cwd: str,
        run_id: str | None = None,
        parent_id: str | None = None,
        source: str = "web",
        progress_total: int | None = None,
    ) -> dict:
        task_id = new_task_id()
        with self._conn() as con:
            con.execute("BEGIN IMMEDIATE")
            while con.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
                task_id = new_task_id()
            seq = con.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM tasks").fetchone()[0]
            con.execute(
                "INSERT INTO tasks (id, kind, queue, title, params, command, cwd, status,"
                " created_at, run_id, parent_id, source, progress_total, seq)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)",
                (
                    task_id, kind, queue, title, json.dumps(params, ensure_ascii=False),
                    json.dumps(command), cwd, _now(), run_id, parent_id, source,
                    progress_total, seq,
                ),
            )
            con.execute("COMMIT")
        return self.get(task_id)

    def get(self, task_id: str) -> dict | None:
        with self._conn() as con:
            return self._row(con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def list(
        self,
        *,
        status: list[str] | None = None,
        kind: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        sql, args = "SELECT * FROM tasks", []
        where = []
        if status:
            where.append(f"status IN ({','.join('?' * len(status))})")
            args.extend(status)
        if kind:
            where.append("kind=?")
            args.append(kind)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY seq DESC LIMIT ?"
        args.append(int(limit))
        with self._conn() as con:
            return [self._row(r) for r in con.execute(sql, args).fetchall()]

    def claim_next(self, queue: str) -> dict | None:
        with self._conn() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT id FROM tasks WHERE status='queued' AND queue=? ORDER BY seq LIMIT 1",
                (queue,),
            ).fetchone()
            if row is None:
                con.execute("COMMIT")
                return None
            con.execute(
                "UPDATE tasks SET status='running', started_at=? WHERE id=? AND status='queued'",
                (_now(), row["id"]),
            )
            con.execute("COMMIT")
        return self.get(row["id"])

    def set_pid(self, task_id: str, pid: int) -> None:
        with self._conn() as con:
            con.execute("UPDATE tasks SET pid=? WHERE id=?", (pid, task_id))

    def set_progress(
        self, task_id: str, done: int, total: int | None, last_line: str | None
    ) -> None:
        with self._conn() as con:
            con.execute(
                "UPDATE tasks SET progress_done=?, progress_total=COALESCE(?, progress_total),"
                " last_line=? WHERE id=?",
                (done, total, last_line, task_id),
            )

    def finish(
        self, task_id: str, status: str, exit_code: int | None, error: str | None
    ) -> None:
        if status not in TERMINAL:
            raise ValueError(f"not a terminal status: {status}")
        with self._conn() as con:
            con.execute(
                "UPDATE tasks SET status=?, exit_code=?, error=?, finished_at=?"
                f" WHERE id=? AND status NOT IN ({','.join('?' * len(TERMINAL))})",
                (status, exit_code, error, _now(), task_id, *sorted(TERMINAL)),
            )

    def cancel_if_queued(self, task_id: str) -> bool:
        with self._conn() as con:
            cur = con.execute(
                "UPDATE tasks SET status='cancelled', finished_at=? WHERE id=? AND status='queued'",
                (_now(), task_id),
            )
            return cur.rowcount == 1

    def count_running(self, queue: str) -> int:
        with self._conn() as con:
            return con.execute(
                "SELECT COUNT(*) FROM tasks WHERE status='running' AND queue=?", (queue,)
            ).fetchone()[0]

    def log_path(self, task_id: str) -> Path:
        return self.log_dir / f"{task_id}.log"

    # ---- families ----------------------------------------------------------------------

    def family_states(self) -> dict[str, dict]:
        with self._conn() as con:
            return {
                r["name"]: {"status": r["status"], "note": r["note"], "first_seen": r["first_seen"]}
                for r in con.execute("SELECT * FROM families").fetchall()
            }

    def touch_families(self, names) -> None:
        now = _now()
        with self._conn() as con:
            con.executemany(
                "INSERT OR IGNORE INTO families (name, first_seen) VALUES (?, ?)",
                [(n, now) for n in names],
            )

    def set_family(self, name: str, *, status: str | None = None, note: str | None = None) -> None:
        if status is not None and status not in {"enabled", "archived"}:
            raise ValueError(f"bad family status: {status}")
        self.touch_families([name])
        with self._conn() as con:
            if status is not None:
                con.execute("UPDATE families SET status=? WHERE name=?", (status, name))
            if note is not None:
                con.execute("UPDATE families SET note=? WHERE name=?", (note, name))
