from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

from backend.orchestrator import FullReportOrchestrator, RunContext
from backend.runtime_store import RuntimeStore
from backend.settings import settings


class RunExecutor:
    def __init__(self, store: RuntimeStore, orchestrator: FullReportOrchestrator) -> None:
        self.store = store
        self.orchestrator = orchestrator
        self.pool = ThreadPoolExecutor(max_workers=settings.worker_pool_size, thread_name_prefix="maer-worker")
        self._futures: dict[str, Future[None]] = {}
        self._lock = Lock()

    def submit(self, context: RunContext) -> None:
        with self._lock:
            if context.run_id in self._futures and not self._futures[context.run_id].done():
                return
            self._futures[context.run_id] = self.pool.submit(self.orchestrator.execute, context)

    def future_state(self, run_id: str) -> str:
        with self._lock:
            future = self._futures.get(run_id)
        if future is None:
            return "not_submitted"
        if future.running():
            return "running"
        if future.done():
            return "done"
        return "queued"

