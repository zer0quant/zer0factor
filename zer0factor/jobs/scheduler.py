"""Start queued tasks within per-queue slot limits, detect lost runners, cancel tasks.

All scheduling decisions live here, so swapping the dispatch layer (e.g. for Celery) later
only replaces this module; the task store and runner stay the same.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from loguru import logger

from zer0factor.jobs.store import TERMINAL, TaskStore

STARTUP_GRACE_SECONDS = 30
KILL_GRACE_SECONDS = 10


def _runner_alive(task: dict) -> bool:
    """The task's pid is alive and is the runner for this very task (pids get reused)."""
    pid = task.get("pid")
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    return task["id"].encode() in cmdline


class Scheduler:
    def __init__(
        self,
        store: TaskStore,
        *,
        slots: dict[str, int],
        spawn: Callable[[dict], int] | None = None,
        on_finished: Callable[[dict], None] | None = None,
        alive: Callable[[dict], bool] = _runner_alive,
    ) -> None:
        self.store = store
        self.slots = dict(slots)
        self.spawn = spawn or self._spawn
        self.on_finished = on_finished
        self.alive = alive
        self._active = {t["id"] for t in store.list(status=["queued", "running"], limit=100000)}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _spawn(self, task: dict) -> int:
        proc = subprocess.Popen(
            [sys.executable, "-m", "zer0factor.jobs.runner", task["id"], str(self.store.db_path)],
            cwd=task["cwd"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return proc.pid

    def tick(self) -> None:
        with self._lock:
            self._reconcile()
            self._notify_finished()
            self._start_queued()

    def _reconcile(self) -> None:
        now = datetime.now()
        for task in self.store.list(status=["running"], limit=100000):
            if task.get("pid"):
                if not self.alive(task):
                    self.store.finish(task["id"], "lost", None, "runner process disappeared")
            elif task.get("started_at"):
                age = (now - datetime.fromisoformat(task["started_at"])).total_seconds()
                if age > STARTUP_GRACE_SECONDS:
                    self.store.finish(task["id"], "lost", None, "runner never started")

    def _notify_finished(self) -> None:
        for task_id in list(self._active):
            task = self.store.get(task_id)
            if task is None or task["status"] in TERMINAL:
                self._active.discard(task_id)
                if task is not None and self.on_finished is not None:
                    try:
                        self.on_finished(task)
                    except Exception:
                        logger.exception(f"on_finished failed for {task_id}")
        self._active.update(
            t["id"] for t in self.store.list(status=["queued", "running"], limit=100000)
        )

    def _start_queued(self) -> None:
        for queue, limit in self.slots.items():
            while self.store.count_running(queue) < limit:
                task = self.store.claim_next(queue)
                if task is None:
                    break
                self._active.add(task["id"])
                try:
                    self.store.set_pid(task["id"], self.spawn(task))
                except Exception as exc:
                    logger.exception(f"failed to spawn runner for {task['id']}")
                    self.store.finish(task["id"], "failed", None, f"spawn failed: {exc}")

    def cancel(self, task_id: str) -> dict | None:
        task = self.store.get(task_id)
        if task is None or task["status"] in TERMINAL:
            return task
        if task["status"] == "queued" and self.store.cancel_if_queued(task_id):
            return self.store.get(task_id)
        task = self.store.get(task_id)
        pid = task.get("pid")
        if pid and self.alive(task):
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

            def escalate():
                time.sleep(KILL_GRACE_SECONDS + 5)
                if not self.alive(task):
                    return
                try:
                    os.killpg(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass

            threading.Thread(target=escalate, daemon=True).start()
        return self.store.get(task_id)

    def start(self, interval: float = 2.0) -> None:
        if self._thread is not None:
            return

        def loop():
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception:
                    logger.exception("scheduler tick failed")
                self._stop.wait(interval)

        self._thread = threading.Thread(target=loop, name="zer0factor-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
