"""Background jobs (contract §10: {"id","status","log","result","error"}).

Jobs run on a small thread pool. Blender builds are additionally serialised by the builder's
own lock, so two agent jobs can think at the same time but never both run Blender.
"""
from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

MAX_LOG_LINES = 400


class JobError(Exception):
    """A failure whose message is meant for the user (shown as the job's error)."""

    def __init__(self, message: str, result: Any = None):
        super().__init__(message)
        self.result = result


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class JobLog:
    def __init__(self, job: dict, lock: threading.Lock):
        self._job = job
        self._lock = lock

    def __call__(self, line: str) -> None:
        with self._lock:
            log = self._job["log"]
            for part in str(line).splitlines() or [""]:
                log.append(part)
            if len(log) > MAX_LOG_LINES:
                del log[: len(log) - MAX_LOG_LINES]


class JobManager:
    def __init__(self, workers: int = 3):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="me3d-job")

    def submit(self, kind: str, fn: Callable[[JobLog], Any]) -> str:
        job_id = "job_" + uuid.uuid4().hex[:10]
        job = {"id": job_id, "kind": kind, "status": "queued", "log": [], "result": None,
               "error": None, "created": now_iso(), "finished": None}
        with self._lock:
            self._jobs[job_id] = job
        self._pool.submit(self._run, job, fn)
        return job_id

    def _run(self, job: dict, fn: Callable[[JobLog], Any]) -> None:
        log = JobLog(job, self._lock)
        with self._lock:
            job["status"] = "running"
        try:
            result = fn(log)
            with self._lock:
                job["result"] = result
                job["status"] = "done"
        except JobError as e:
            with self._lock:
                job["error"] = str(e)
                job["result"] = e.result
                job["status"] = "error"
        except Exception as e:  # unexpected: keep the traceback in the log, a sentence in error
            log(traceback.format_exc())
            with self._lock:
                job["error"] = f"{type(e).__name__}: {e}"
                job["status"] = "error"
        finally:
            with self._lock:
                job["finished"] = now_iso()

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return {"id": job["id"], "kind": job["kind"], "status": job["status"],
                    "log": list(job["log"]), "result": job["result"], "error": job["error"],
                    "created": job["created"], "finished": job["finished"]}

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
