import threading

from zer0factor.jobs.store import TaskStore


def _new(store, **kw):
    args = dict(kind="evaluate", queue="heavy", title="t", params={"factors": ["fa"]},
                command=["python", "-c", "print(1)"], cwd="/tmp")
    args.update(kw)
    return store.create(**args)


def test_create_and_get_roundtrip(tmp_path):
    store = TaskStore(tmp_path / "wb.db")
    task = _new(store, run_id="r1")
    got = store.get(task["id"])
    assert got["params"] == {"factors": ["fa"]}
    assert got["command"] == ["python", "-c", "print(1)"]
    assert got["status"] == "queued"
    assert got["run_id"] == "r1"
    assert got["source"] == "web"
    assert store.get("nope") is None


def test_claim_next_is_fifo_and_atomic(tmp_path):
    store = TaskStore(tmp_path / "wb.db")
    t1, t2 = _new(store), _new(store)
    assert store.claim_next("heavy")["id"] == t1["id"]
    assert store.claim_next("heavy")["id"] == t2["id"]
    assert store.claim_next("heavy") is None
    assert store.get(t1["id"])["status"] == "running"

    ids = [_new(store)["id"] for _ in range(20)]
    claimed: list[str] = []
    lock = threading.Lock()

    def worker():
        other = TaskStore(tmp_path / "wb.db")
        while (t := other.claim_next("heavy")) is not None:
            with lock:
                claimed.append(t["id"])

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(claimed) == sorted(ids)


def test_finish_does_not_override_terminal(tmp_path):
    store = TaskStore(tmp_path / "wb.db")
    task = _new(store)
    store.finish(task["id"], "cancelled", None, None)
    store.finish(task["id"], "failed", 1, "boom")
    got = store.get(task["id"])
    assert got["status"] == "cancelled"
    assert got["finished_at"]


def test_progress_and_pid(tmp_path):
    store = TaskStore(tmp_path / "wb.db")
    task = _new(store)
    store.set_pid(task["id"], 123)
    store.set_progress(task["id"], 2, 5, "line")
    got = store.get(task["id"])
    assert (got["pid"], got["progress_done"], got["progress_total"], got["last_line"]) == (
        123, 2, 5, "line")
    assert store.log_path(task["id"]).name == f"{task['id']}.log"


def test_list_filters_by_status_and_kind(tmp_path):
    store = TaskStore(tmp_path / "wb.db")
    a = _new(store)
    b = _new(store, kind="warm", queue="light")
    store.finish(a["id"], "succeeded", 0, None)
    assert [t["id"] for t in store.list()] == [b["id"], a["id"]]
    assert [t["id"] for t in store.list(status=["queued"])] == [b["id"]]
    assert [t["id"] for t in store.list(kind="evaluate")] == [a["id"]]
    assert store.count_running("light") == 0


def test_family_states_default_enabled(tmp_path):
    store = TaskStore(tmp_path / "wb.db")
    store.touch_families(["fam_a", "fam_b"])
    states = store.family_states()
    assert states["fam_a"]["status"] == "enabled"
    assert states["fam_a"]["first_seen"]
    store.set_family("fam_a", status="archived", note="old")
    store.touch_families(["fam_a"])
    states = store.family_states()
    assert states["fam_a"]["status"] == "archived"
    assert states["fam_a"]["note"] == "old"
