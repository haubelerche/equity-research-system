"""Unit tests for the fast-render vs full-pipeline routing in the orchestrator."""
import backend.reporting.report_delivery as rd
from backend.orchestrator import FullReportOrchestrator, RunContext


class FakeStore:
    def __init__(self, status: str = "auto_exported") -> None:
        self.states: list[tuple] = []
        self.progress: list[dict] = []
        self._status = status

    def update_run_state(self, run_id, status, stage, flags=None, finished=False):
        self.states.append((status, stage, finished))

    def update_run_progress(self, run_id, **kw):
        self.progress.append(kw)

    def get_run(self, run_id):
        return {"status": self._status}


def _orchestrator(store: FakeStore) -> FullReportOrchestrator:
    # Bypass __init__ so we don't build a real ResearchGraphRunner.
    orch = FullReportOrchestrator.__new__(FullReportOrchestrator)
    orch.store = store
    return orch


def _ctx(flags: dict) -> RunContext:
    return RunContext(
        run_id="r1", ticker="DHG", run_type="full_report",
        objective="x", policy={}, flags=flags,
    )


def test_fast_render_renders_from_source_run_and_marks_exported(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(rd, "render_and_store", lambda ticker, run_id, **kw: calls.append((ticker, run_id)))
    store = FakeStore()
    _orchestrator(store)._fast_render(_ctx({"generate_mode": "fast_render", "source_run_id": "src1"}))

    assert calls == [("DHG", "src1")]
    assert store.states[-1] == ("auto_exported", "PUBLISH", True)


def test_fast_render_marks_failed_with_blocking_reason(monkeypatch):
    def boom(ticker, run_id, **kw):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(rd, "render_and_store", boom)
    monkeypatch.setattr(rd, "existing_client_report_available", lambda ticker: False)
    store = FakeStore()
    _orchestrator(store)._fast_render(_ctx({"generate_mode": "fast_render", "source_run_id": "src1"}))

    assert store.states[-1] == ("failed", "PUBLISH", True)
    failure = next(p for p in store.progress if "blocking_reason" in p)
    assert failure["source_run_id"] == "src1"
    assert "render exploded" in failure["render_error"]


def test_fast_render_uses_existing_export_when_rerender_fails(monkeypatch):
    def boom(ticker, run_id, **kw):
        raise RuntimeError("run artifacts unavailable")

    monkeypatch.setattr(rd, "render_and_store", boom)
    monkeypatch.setattr(rd, "existing_client_report_available", lambda ticker: True)
    store = FakeStore()
    _orchestrator(store)._fast_render(_ctx({"generate_mode": "fast_render", "source_run_id": "src1"}))

    assert store.states[-1] == ("auto_exported", "PUBLISH", True)
    assert any(p.get("substep") == "export_available" for p in store.progress)
    fallback = next(p for p in store.progress if p.get("substep") == "export_available")
    assert fallback["source_run_id"] == "src1"
    assert "run artifacts unavailable" in fallback["render_error"]
    assert "ghi đè" in fallback["detail"]
    assert not any("blocking_reason" in p for p in store.progress)


def test_render_after_run_renders_only_when_renderable(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(rd, "render_and_store", lambda ticker, run_id, **kw: calls.append((ticker, run_id)))

    _orchestrator(FakeStore(status="auto_exported"))._render_after_run(_ctx({}))
    assert calls == [("DHG", "r1")]

    calls.clear()
    _orchestrator(FakeStore(status="blocked"))._render_after_run(_ctx({}))
    assert calls == []
