from pathlib import Path
from fastapi.testclient import TestClient
from backend.api import create_app, mount_frontend


def test_serves_spa_index_when_dist_present(tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    app = create_app(check_schema_on_startup=False)
    mount_frontend(app, dist)
    client = TestClient(app)
    # unknown non-API path returns the SPA index (200), not 404
    resp = client.get("/eval")
    assert resp.status_code == 200
    assert "app" in resp.text
    # health (API) still works and is not shadowed
    assert client.get("/health").json()["status"] == "ok"
