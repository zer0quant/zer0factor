"""Factor family listing for the workbench.

Discovery runs ``zer0factor.cli families --json`` in a subprocess: importing family code in
the server would let a broken (or slow) family module take the server down, and a long-lived
process would keep serving stale modules after the code changes.
"""

from __future__ import annotations

import json
import subprocess
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from zer0factor.config import Config
from zer0factor.jobs.specs import cli_head
from zer0factor.jobs.store import TaskStore

DISCOVERY_TIMEOUT = 120
NEW_DAYS = 7


class DiscoveryError(RuntimeError):
    pass


def run_discovery(cfg: Config, config_path: Path) -> dict:
    command = [*cli_head(cfg, config_path), "families", "--json"]
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=DISCOVERY_TIMEOUT, cwd=Path.cwd()
        )
    except subprocess.TimeoutExpired as exc:
        raise DiscoveryError(f"family discovery timed out after {DISCOVERY_TIMEOUT}s") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-15:]
        raise DiscoveryError("family discovery failed:\n" + "\n".join(tail))
    # Family modules may print while importing; the JSON document is the last line.
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        raise DiscoveryError("family discovery printed nothing")
    return json.loads(lines[-1])


def _latest_partition(factor_dir: Path) -> str | None:
    if not factor_dir.is_dir():
        return None
    dates = [p.name[5:] for p in factor_dir.iterdir() if p.name.startswith("date=")]
    return max(dates) if dates else None


class FamilyCatalog:
    def __init__(
        self,
        cfg: Config,
        config_path: Path,
        store: TaskStore,
        run: Callable[[], dict] | None = None,
    ) -> None:
        self.cfg = cfg
        self.store = store
        self.run = run or (lambda: run_discovery(cfg, config_path))
        self._raw: list[dict] | None = None
        self.scanned_at: datetime | None = None
        self._lock = threading.Lock()
        self._end_cache: dict[str, tuple[float, str | None]] = {}

    def _discovered(self, refresh: bool) -> list[dict]:
        with self._lock:
            if self._raw is None or refresh:
                self._raw = list(self.run()["families"])
                self.scanned_at = datetime.now()
                self.store.touch_families(f["name"] for f in self._raw if not f["error"])
            return self._raw

    def valid_names(self) -> set[str]:
        return {f["name"] for f in self._discovered(False) if not f["error"]}

    def _data_end(self, name: str) -> str | None:
        path = Path(self.cfg.factor_dir) / name
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        hit = self._end_cache.get(name)
        if hit and hit[0] == mtime:
            return hit[1]
        end = _latest_partition(path)
        self._end_cache[name] = (mtime, end)
        return end

    def list(self, refresh: bool = False) -> list[dict]:
        discovered = self._discovered(refresh)
        states = self.store.family_states()
        builds: dict[str, dict] = {}
        for task in self.store.list(kind="build", limit=1000):  # newest first
            builds.setdefault(task["params"].get("family"), task)
        factor_dir = Path(self.cfg.factor_dir)
        stored_all = {p.name for p in factor_dir.iterdir()} if factor_dir.is_dir() else set()
        now = datetime.now()
        rows = []
        for fam in discovered:
            state = states.get(fam["name"], {})
            first_seen = state.get("first_seen")
            stored = [n for n in fam["outputs"] if n in stored_all]
            last = builds.get(fam["name"])
            rows.append(
                {
                    **fam,
                    "status": state.get("status", "enabled"),
                    "note": state.get("note", ""),
                    "first_seen": first_seen,
                    "is_new": bool(
                        first_seen
                        and now - datetime.fromisoformat(first_seen) < timedelta(days=NEW_DAYS)
                    ),
                    "stored": len(stored),
                    "stored_names": stored,
                    "data_end": self._data_end(fam["raw_names"][0]) if fam["raw_names"] else None,
                    "last_task": (
                        {"id": last["id"], "status": last["status"], "created_at": last["created_at"]}
                        if last
                        else None
                    ),
                }
            )
        return rows
