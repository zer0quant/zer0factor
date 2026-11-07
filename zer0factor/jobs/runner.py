"""Detached task runner: ``python -m zer0factor.jobs.runner <task_id> <db_path>``.

Started by the scheduler in its own session (process group), so restarting the web server
does not stop it. It runs the task's CLI command, streams output to the task log, keeps
progress in the store and writes the final status itself.
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from zer0factor.jobs.progress import Progress
from zer0factor.jobs.store import TaskStore

KILL_GRACE_SECONDS = 10
PROGRESS_INTERVAL = 1.0
ERROR_TAIL_LINES = 20


def _config_path(command: list[str]) -> Path | None:
    if "--config" in command:
        i = command.index("--config")
        if i + 1 < len(command):
            return Path(command[i + 1])
    return None


def _enqueue_warm(store: TaskStore, task: dict) -> None:
    from zer0factor.config import load_config
    from zer0factor.jobs.specs import build_spec
    from zer0factor.web.runs import scan_runs

    config_path = _config_path(task["command"])
    if config_path is None or not task.get("run_id"):
        return
    cfg = load_config(config_path)
    runs = {r.run_id: r for r in scan_runs(Path(cfg.web.evaluations_dir))}
    run = runs.get(task["run_id"])
    if run is None:
        return
    spec = build_spec(
        "warm",
        {"run_id": run.run_id},
        cfg=cfg,
        config_path=config_path,
        known_factors=set(),
        known_families=set(),
        known_runs=set(runs),
        run_factor_counts={run.run_id: len(run.factor_names)},
    )
    store.create(
        kind=spec.kind,
        queue=spec.queue,
        title=spec.title,
        params=spec.params,
        command=spec.command,
        cwd=task["cwd"],
        run_id=spec.run_id,
        parent_id=task["id"],
        source=task.get("source") or "web",
        progress_total=spec.progress_total,
    )


def _mark_cancelled_run(task: dict) -> None:
    from zer0factor.config import load_config

    config_path = _config_path(task["command"])
    if not task.get("run_id") or config_path is None:
        return
    try:
        run_dir = Path(load_config(config_path).web.evaluations_dir) / task["run_id"]
    except Exception:
        return
    if run_dir.is_dir():
        (run_dir / ".cancelled").write_text(f"cancelled by task {task['id']}\n")


def run_task(task_id: str, db_path: str) -> int:
    store = TaskStore(Path(db_path))
    task = store.get(task_id)
    if task is None:
        print(f"unknown task {task_id}", file=sys.stderr)
        return 2
    store.set_pid(task_id, os.getpid())

    cancelled = threading.Event()
    log_path = store.log_path(task_id)
    progress = Progress(task["kind"], task.get("progress_total"))
    tail: deque[str] = deque(maxlen=ERROR_TAIL_LINES)

    with open(log_path, "a", encoding="utf-8", errors="replace") as log:
        log.write("$ " + shlex.join(task["command"]).replace("\n", "\\n") + "\n")
        log.flush()
        try:
            child = subprocess.Popen(
                task["command"],
                cwd=task["cwd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                errors="replace",
                bufsize=1,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        except OSError as exc:
            log.write(f"failed to start: {exc}\n")
            store.finish(task_id, "failed", None, str(exc))
            return 1

        def on_term(signum, frame):
            cancelled.set()
            if child.poll() is None:
                child.terminate()

                def killer():
                    try:
                        child.wait(KILL_GRACE_SECONDS)
                    except subprocess.TimeoutExpired:
                        child.kill()

                threading.Thread(target=killer, daemon=True).start()

        signal.signal(signal.SIGTERM, on_term)
        signal.signal(signal.SIGINT, on_term)

        last_flush = 0.0
        assert child.stdout is not None
        for line in child.stdout:
            log.write(line)
            log.flush()
            tail.append(line.rstrip())
            if progress.feed(line) and time.monotonic() - last_flush >= PROGRESS_INTERVAL:
                store.set_progress(task_id, progress.done, progress.total, progress.last_line)
                last_flush = time.monotonic()
        code = child.wait()
        store.set_progress(task_id, progress.done, progress.total, progress.last_line)
        log.write(f"\n[exit {code}]\n")

    if cancelled.is_set():
        _mark_cancelled_run(task)
        store.finish(task_id, "cancelled", code, None)
        return code
    if code == 0:
        store.finish(task_id, "succeeded", 0, None)
        if task["kind"] == "evaluate":
            try:
                _enqueue_warm(store, store.get(task_id))
            except Exception as exc:  # warm is best effort; the evaluation itself succeeded
                with open(log_path, "a", encoding="utf-8") as log:
                    log.write(f"failed to enqueue cache warm-up: {exc!r}\n")
        return 0
    store.finish(task_id, "failed", code, "\n".join(tail))
    return code


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("usage: python -m zer0factor.jobs.runner <task_id> <db_path>", file=sys.stderr)
        return 2
    return run_task(argv[0], argv[1])


if __name__ == "__main__":
    sys.exit(main())
