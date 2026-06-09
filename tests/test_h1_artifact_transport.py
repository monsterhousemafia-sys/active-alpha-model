from __future__ import annotations

import json
import pickle
from pathlib import Path

from analytics.h1_artifact_transport import (
    ensure_h1_run_assets,
    ingest_prep_artifact,
    list_prep_artifacts,
    resolve_h1_asset_path,
    serve_h1_asset,
    upload_prep_to_hub,
    validate_join_token,
)


def _seed(root: Path) -> tuple[Path, str]:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control/preview_federation.json").write_text(
        json.dumps({"join_token": "tok-secret", "enabled": True}),
        encoding="utf-8",
    )
    run = root / "validation_runs/20260606T000000Z_DAILY_ALPHA_H1"
    run.mkdir(parents=True)
    (run / "features.parquet").write_bytes(b"PARQUET-DATA")
    (run / "run_config_snapshot.txt").write_text("rebalance_every=1\n", encoding="utf-8")
    rel = str(run.relative_to(root)).replace("\\", "/")
    return run, rel


def test_validate_join_token(tmp_path: Path) -> None:
    _seed(tmp_path)
    assert validate_join_token(tmp_path, "tok-secret") is None
    assert validate_join_token(tmp_path, "wrong") == "join_token ungültig"


def test_resolve_and_serve_asset(tmp_path: Path) -> None:
    _, rel = _seed(tmp_path)
    path = resolve_h1_asset_path(tmp_path, rel, "features.parquet")
    assert path is not None
    assert path.read_bytes() == b"PARQUET-DATA"
    got, mime, err = serve_h1_asset(tmp_path, run_rel=rel, filename="features.parquet", join_token="tok-secret")
    assert err is None and got is not None
    assert mime == "application/octet-stream"


def test_ingest_prep_artifact(tmp_path: Path) -> None:
    _seed(tmp_path)
    payload = {0: {"risk_on": True, "target_weights": {"AAPL": 0.1}}}
    data = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    out = ingest_prep_artifact(
        tmp_path,
        chunk_id="naive-prep-0001",
        data=data,
        worker_id="w-test",
        join_token="tok-secret",
    )
    assert out.get("ok") is True
    stored = tmp_path / "evidence/h1_naive_prep_chunks/naive-prep-0001.pkl"
    assert stored.is_file()
    assert pickle.loads(stored.read_bytes()) == payload
    listing = list_prep_artifacts(tmp_path)
    assert listing["count"] == 1


def test_upload_roundtrip_via_hub(tmp_path: Path, monkeypatch) -> None:
    from http.server import HTTPServer
    import threading

    _, rel = _seed(tmp_path)
    king = tmp_path
    worker_root = tmp_path / "worker"
    worker_root.mkdir()
    (worker_root / "control").mkdir(parents=True)
    (worker_root / "control/preview_worker_join.json").write_text(
        json.dumps({"hub_join_url": "http://127.0.0.1:0", "join_token": "tok-secret", "role": "worker"}),
        encoding="utf-8",
    )
    artifact = worker_root / "evidence/h1_naive_prep_chunks/naive-prep-0002.pkl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(pickle.dumps({1: {"risk_on": False}}, protocol=pickle.HIGHEST_PROTOCOL))

    from tools.preview_hub import make_handler

    handler_cls = make_handler(tmp_path, 0)
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        hub = f"http://127.0.0.1:{port}"
        out = upload_prep_to_hub(
            hub,
            artifact,
            chunk_id="naive-prep-0002",
            run_dir=rel,
            join_token="tok-secret",
            worker_id="w-remote",
        )
        assert out.get("ok") is True
        king_path = tmp_path / "evidence/h1_naive_prep_chunks/naive-prep-0002.pkl"
        assert king_path.is_file()
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_ensure_h1_run_assets_download(tmp_path: Path, monkeypatch) -> None:
    _, rel = _seed(tmp_path)
    king = tmp_path
    worker_root = tmp_path / "worker"
    worker_root.mkdir()
    (worker_root / "control").mkdir(parents=True)
    (worker_root / "control/preview_worker_join.json").write_text(
        json.dumps({"join_token": "tok-secret"}),
        encoding="utf-8",
    )

    from tools.preview_hub import make_handler
    from http.server import HTTPServer
    import threading

    handler_cls = make_handler(king, 0)
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        hub = f"http://127.0.0.1:{port}"
        out = ensure_h1_run_assets(worker_root, hub, rel, join_token="tok-secret")
        assert out.get("ok") is True
        assert (worker_root / rel / "features.parquet").read_bytes() == b"PARQUET-DATA"
    finally:
        server.shutdown()
        thread.join(timeout=2)
