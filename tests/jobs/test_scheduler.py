import subprocess
import sys

from zer0factor.jobs.scheduler import Scheduler
from zer0factor.jobs.store import TaskStore


def _new(store, queue="heavy", kind="evaluate"):
    return store.create(kind=kind, queue=queue, title="t", params={}, command=["true"],
                        cwd="/tmp")


class FakeSpawn:
    def __init__(self):
        self.started = []

    def __call__(self, task):
        self.started.append(task["id"])
        return 999999


def test_tick_respects_slots(tmp_path):
    store = TaskStore(tmp_path / "wb.db")
    heavy = [_new(store) for _ in range(3)]
    light = _new(store, queue="light", kind="warm")
    spawn = FakeSpawn()
    sched = Scheduler(store, slots={"heavy": 1, "light": 2}, spawn=spawn, alive=lambda t: True)
    sched.tick()
    assert spawn.started == [heavy[0]["id"], light["id"]]
    assert store.get(heavy[0]["id"])["pid"] == 999999
    sched.tick()
    assert len(spawn.started) == 2  # heavy slot still busy


def test_reconcile_marks_dead_pid_lost(tmp_path):
    store = TaskStore(tmp_path / "wb.db")
    task = _new(store)
    store.claim_next("heavy")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    store.set_pid(task["id"], dead.pid)
    Scheduler(store, slots={"heavy": 0}, spawn=FakeSpawn()).tick()
    assert store.get(task["id"])["status"] == "lost"


def test_reconcile_keeps_live_runner(tmp_path):
    store = TaskStore(tmp_path / "wb.db")
    task = _new(store)
    store.claim_next("heavy")
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", task["id"]]
    )
    try:
        store.set_pid(task["id"], proc.pid)
        Scheduler(store, slots={"heavy": 0}, spawn=FakeSpawn()).tick()
        assert store.get(task["id"])["status"] == "running"
        # a live pid that belongs to some other program does not count
        other = _new(store)
        store.claim_next("heavy")
        store.set_pid(other["id"], proc.pid)
        Scheduler(store, slots={"heavy": 0}, spawn=FakeSpawn()).tick()
        assert store.get(other["id"])["status"] == "lost"
    finally:
        proc.kill()


def test_on_finished_called_once(tmp_path):
    store = TaskStore(tmp_path / "wb.db")
    old = _new(store)
    store.finish(old["id"], "succeeded", 0, None)
    seen = []
    sched = Scheduler(store, slots={"heavy": 1}, spawn=FakeSpawn(), alive=lambda t: True,
                      on_finished=lambda t: seen.append(t["id"]))
    task = _new(store)
    sched.tick()
    store.finish(task["id"], "succeeded", 0, None)
    sched.tick()
    sched.tick()
    assert seen == [task["id"]]  # tasks already finished at startup are not re-announced


def test_cancel_queued(tmp_path):
    store = TaskStore(tmp_path / "wb.db")
    task = _new(store)
    sched = Scheduler(store, slots={"heavy": 0}, spawn=FakeSpawn())
    assert sched.cancel(task["id"])["status"] == "cancelled"
    assert sched.cancel(task["id"])["status"] == "cancelled"
