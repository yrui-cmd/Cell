"""Persist verified queue observations and the first observed processing time."""
import time

from transfer import check, order_lock, read, write

STATE = "job-progress.json"
POLL_SECONDS = 5
SECONDS_PER_PAGE = 15 * 60
STATUSES = {"queued", "processing", "completed", "failed", "cancelled", "expired"}


def load(root, order):
    path = root / STATE
    state = read(path) if path.exists() else {}
    check(not state or state.get("job_id") == order["job_id"], "进度记录属于其他订单")
    return state


def observe(root, order, reply, now=None):
    check(reply.get("job_id") == order["job_id"] and reply.get("status") in STATUSES,
          "订单进度响应不匹配")
    now = time.time() if now is None else now
    with order_lock(root / "job-progress.lock"):
        state = load(root, order)
        if state.get("checked_at", 0) > now:
            return state
        status = reply["status"]
        queue = reply.get("queue")
        queue = queue if isinstance(queue, dict) and status in {"queued", "processing"} else None
        if queue is not None:
            queue = {key: value for key, value in queue.items()
                     if key in {"position", "ahead", "waiting", "processing", "as_of_unix"}
                     and type(value) in {int, float} and value >= 0}
            if status == "processing":
                queue.update(position=None, ahead=None)
        state.update(job_id=order["job_id"], status=status, queue=queue, checked_at=now)
        if status == "processing":
            # This API does not promise a server-side start timestamp.
            state.setdefault("processing_started_at_unix", now)
        if status in STATUSES - {"queued", "processing"}:
            state.setdefault("finished_at_unix", now)
        write(root / STATE, state)
        return state
