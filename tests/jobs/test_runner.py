import os
import signal
import subprocess
import sys
import time

import pytest

from zer0factor.jobs.store import TaskStore


def _write_settings(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text(f"""
[zer0share]
data_dir = "{tmp_path / 'zs'}"
[paths]
factor_dir = "{tmp_path / 'factors'}"
db_path = "{tmp_path / 'f.duckdb'}"
log_path = "{tmp_path / 'f.log'}"
[factor]
universe = "all"
start_date = "20160101"
end_date = ""
[web]
evaluations_dir = "{tmp_path / 'evals'}"
state_dir = "{tmp_path / 'wb'}"
""")
    return path


def _task(store, tmp_path, script, *, kind="evaluate", run_id=None, total=None):
    settings = _write_settings(tmp_path)
    command = [sys.executable, "-c", script, "--config", str(settings)]
    return store.create(kind=kind, queue="heavy", title="t", params={}, command=command,
                        cwd=str(tmp_path), run_id=run_id, progress_total=total)


def _run(task_id, db):
    return subprocess.Popen(
        [sys.executable, "-m", "zer0factor.jobs.runner", task_id, str(db)],
        start_new_session=True,
    )


def test_runner_success_writes_log_and_status(tmp_path):
    (tmp_path / "evals" / "r1" / "factors" / "fa").mkdir(parents=True)
    (tmp_path / "evals" / "r1" / "metadata.json").write_text('{"factor_names": ["fa"]}')
    store = TaskStore(tmp_path / "wb" / "workbench.db")
    script = "\n".join(
        f"print('INFO | evaluation_factor_finished factor=f{i}', flush=True)" for i in range(3)
    )
    task = _task(store, tmp_path, script, run_id="r1", total=3)
    assert _run(task["id"], store.db_path).wait(30) == 0
    got = store.get(task["id"])
    assert got["status"] == "succeeded", got
    assert got["exit_code"] == 0
    assert (got["progress_done"], got["progress_total"]) == (3, 3)
    assert got["pid"]
    lines = store.log_path(task["id"]).read_text().splitlines()
    assert lines[0].startswith("$ ")  # the command line heads the log
    assert sum("evaluation_factor_finished" in ln for ln in lines[1:]) == 3
    children = [t for t in store.list() if t["parent_id"] == task["id"]]
    assert len(children) == 1
    child = children[0]
    assert child["kind"] == "warm" and child["status"] == "queued"
    assert child["command"][-4:] == ["--run", "r1", "--workers", "8"]


def test_runner_failure_captures_tail(tmp_path):
    store = TaskStore(tmp_path / "wb" / "workbench.db")
    task = _task(store, tmp_path, "import sys; print('first'); print('last words'); sys.exit(3)",
                 kind="build")
    assert _run(task["id"], store.db_path).wait(30) != 0
    got = store.get(task["id"])
    assert got["status"] == "failed"
    assert got["exit_code"] == 3
    assert "last words" in got["error"]
    assert [t for t in store.list() if t["parent_id"] == task["id"]] == []


def test_runner_cancel_kills_child_and_marks_run(tmp_path):
    run_dir = tmp_path / "evals" / "r2"
    run_dir.mkdir(parents=True)
    store = TaskStore(tmp_path / "wb" / "workbench.db")
    script = "import time, os; print(os.getpid(), flush=True); time.sleep(60)"
    task = _task(store, tmp_path, script, run_id="r2")
    proc = _run(task["id"], store.db_path)
    log = store.log_path(task["id"])
    deadline = time.time() + 20
    while time.time() < deadline and not (log.exists() and len(log.read_text().splitlines()) > 1):
        time.sleep(0.1)
    child_pid = int(log.read_text().splitlines()[1])
    os.killpg(proc.pid, signal.SIGTERM)
    proc.wait(30)
    got = store.get(task["id"])
    assert got["status"] == "cancelled", got
    assert (run_dir / ".cancelled").exists()
    with pytest.raises(ProcessLookupError):
        for _ in range(50):
            os.kill(child_pid, 0)
            time.sleep(0.1)
