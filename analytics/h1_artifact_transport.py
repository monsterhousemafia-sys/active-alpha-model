"""H1 Asset-Download (König→Worker) und Prep-Upload (Worker→König) über Hub/Tunnel."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode, urlparse

from aa_safe_io import atomic_write_json

_PREP_DIR_REL = Path("evidence/h1_naive_prep_chunks")
_EVIDENCE_REL = Path("evidence/h1_artifact_transport_latest.json")
_CHUNK_ID_RE = re.compile(r"^naive-prep-\d{4}$")
_REQUIRED_SYNC = ("features.parquet", "run_config_snapshot.txt")
_ALLOWED_ASSETS = frozenset(
    {
        "features.parquet",
        "prediction_cache.pkl",
        "prediction_cache_meta.json",
        "path_sim_checkpoint.pkl",
        "path_sim_checkpoint_meta.json",
        "run_config_snapshot.txt",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _is_remote_hub(hub_url: str) -> bool:
    host = (urlparse(str(hub_url or "").strip()).hostname or "").lower()
    return host not in ("127.0.0.1", "localhost", "::1", "")


def _join_token(root: Path) -> str:
    from analytics.preview_federation import federation_config, worker_join_config

    doc = worker_join_config(root)
    token = str(doc.get("join_token") or "").strip()
    if token:
        return token
    return str(federation_config(root).get("join_token") or "").strip()


def validate_join_token(root: Path, token: str) -> Optional[str]:
    root = Path(root)
    expected = _join_token(root)
    if not expected:
        return None
    got = str(token or "").strip()
    if got != expected:
        return "join_token ungültig"
    return None


def _normalize_run_rel(run_rel: str) -> Optional[str]:
    rel = str(run_rel or "").strip().replace("\\", "/").strip("/")
    if not rel or ".." in rel.split("/"):
        return None
    if not rel.startswith("validation_runs/"):
        return None
    return rel


def resolve_h1_asset_path(root: Path, run_rel: str, filename: str) -> Optional[Path]:
    root = Path(root)
    rel = _normalize_run_rel(run_rel)
    name = str(filename or "").strip()
    if not rel or name not in _ALLOWED_ASSETS:
        return None
    path = (root / rel / name).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def serve_h1_asset(
    root: Path,
    *,
    run_rel: str,
    filename: str,
    join_token: str,
) -> Tuple[Optional[Path], Optional[str], Optional[str]]:
    """König: Asset-Pfad für GET /api/h1/asset."""
    err = validate_join_token(root, join_token)
    if err:
        return None, None, err
    path = resolve_h1_asset_path(root, run_rel, filename)
    if path is None:
        return None, None, "Asset fehlt oder nicht erlaubt"
    mime = "application/octet-stream"
    if filename.endswith(".json") or filename.endswith(".txt"):
        mime = "text/plain; charset=utf-8"
    return path, mime, None


def ingest_prep_artifact(
    root: Path,
    *,
    chunk_id: str,
    data: bytes,
    worker_id: str = "",
    join_token: str = "",
) -> Dict[str, Any]:
    """König: Worker-Prep-Chunk speichern."""
    root = Path(root)
    err = validate_join_token(root, join_token)
    if err:
        return {"ok": False, "message_de": err}
    cid = str(chunk_id or "").strip()
    if not _CHUNK_ID_RE.match(cid):
        return {"ok": False, "message_de": "chunk_id ungültig"}
    if not data:
        return {"ok": False, "message_de": "leerer Upload"}

    out_dir = root / _PREP_DIR_REL
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{cid}.pkl"
    tmp = out_path.with_suffix(".pkl.part")
    tmp.write_bytes(data)
    tmp.replace(out_path)

    doc = {
        "ok": True,
        "chunk_id": cid,
        "artifact": str(out_path.relative_to(root)).replace("\\", "/"),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "worker_id": str(worker_id or "").strip() or None,
        "ingested_at_utc": _utc_now(),
    }
    _append_transport_log(root, doc)
    return doc


def ingest_prep_artifact_from_request(
    root: Path,
    *,
    headers: Any,
    body: bytes,
    query: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    qs = query or {}
    join_token = str(headers.get("X-AA-Join-Token") or (qs.get("join_token") or [""])[0] or "").strip()
    chunk_id = str(headers.get("X-AA-Chunk-Id") or (qs.get("chunk_id") or [""])[0] or "").strip()
    worker_id = str(headers.get("X-AA-Worker-Id") or (qs.get("worker_id") or [""])[0] or "").strip()
    return ingest_prep_artifact(
        root,
        chunk_id=chunk_id,
        data=body,
        worker_id=worker_id,
        join_token=join_token,
    )


def _append_transport_log(root: Path, entry: Dict[str, Any]) -> None:
    path = root / _EVIDENCE_REL
    doc: Dict[str, Any] = {"schema_version": 1, "ingested": [], "updated_at_utc": _utc_now()}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                doc = loaded
        except (json.JSONDecodeError, OSError):
            pass
    ingested = list(doc.get("ingested") or [])
    ingested.append(entry)
    doc["ingested"] = ingested[-80:]
    doc["updated_at_utc"] = _utc_now()
    doc["chunks_on_disk"] = len(list((root / _PREP_DIR_REL).glob("naive-prep-*.pkl")))
    atomic_write_json(path, doc)


def list_prep_artifacts(root: Path) -> Dict[str, Any]:
    root = Path(root)
    prep_dir = root / _PREP_DIR_REL
    files = []
    if prep_dir.is_dir():
        for p in sorted(prep_dir.glob("naive-prep-*.pkl")):
            files.append({"chunk_id": p.stem, "bytes": p.stat().st_size, "path": str(p.relative_to(root))})
    return {"ok": True, "count": len(files), "files": files, "updated_at_utc": _utc_now()}


def download_h1_asset(
    hub_url: str,
    root: Path,
    run_rel: str,
    filename: str,
    *,
    join_token: str = "",
    timeout: float = 900.0,
) -> Dict[str, Any]:
    """Worker: ein Asset vom König laden."""
    root = Path(root)
    rel = _normalize_run_rel(run_rel)
    name = str(filename or "").strip()
    if not rel or name not in _ALLOWED_ASSETS:
        return {"ok": False, "message_de": "Ungültiger Asset-Pfad"}
    token = str(join_token or _join_token(root)).strip()
    if not token:
        return {"ok": False, "message_de": "join_token fehlt"}

    hub = str(hub_url or "").rstrip("/")
    qs = urlencode({"run_dir": rel, "file": name, "join_token": token})
    url = f"{hub}/api/h1/asset?{qs}"
    dest = root / rel / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return {"ok": False, "message_de": f"HTTP {resp.status}"}
            with open(tmp, "wb") as fh:
                while True:
                    block = resp.read(1024 * 1024)
                    if not block:
                        break
                    fh.write(block)
        tmp.replace(dest)
        return {
            "ok": True,
            "file": name,
            "path": str(dest.relative_to(root)).replace("\\", "/"),
            "bytes": dest.stat().st_size,
        }
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            detail = str(exc)
        return {"ok": False, "message_de": f"Download {name}: {detail}"}
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        return {"ok": False, "message_de": str(exc)[:200]}


def ensure_h1_run_assets(
    root: Path,
    hub_url: str,
    run_rel: str,
    *,
    join_token: str = "",
    required: Tuple[str, ...] = _REQUIRED_SYNC,
) -> Dict[str, Any]:
    """Worker: fehlende H1-Run-Assets vom König holen."""
    root = Path(root)
    rel = _normalize_run_rel(run_rel)
    if not rel:
        return {"ok": False, "message_de": "run_dir ungültig"}
    token = str(join_token or _join_token(root)).strip()
    if not hub_url or not token:
        return {"ok": False, "message_de": "Hub oder join_token fehlt"}

    synced: List[str] = []
    errors: List[str] = []
    for name in required:
        dest = root / rel / name
        if dest.is_file() and dest.stat().st_size > 0:
            synced.append(f"skip {name}")
            continue
        out = download_h1_asset(hub_url, root, rel, name, join_token=token)
        if out.get("ok"):
            synced.append(f"got {name}")
        else:
            errors.append(str(out.get("message_de") or name))

    ok = not errors and (root / rel / "features.parquet").is_file()
    return {
        "ok": ok,
        "synced": synced,
        "errors": errors,
        "message_de": "Assets bereit" if ok else (errors[0] if errors else "features.parquet fehlt"),
    }


def upload_prep_to_hub(
    hub_url: str,
    local_path: Path,
    *,
    chunk_id: str,
    run_dir: str = "",
    join_token: str = "",
    worker_id: str = "",
    timeout: float = 300.0,
) -> Dict[str, Any]:
    """Worker: Prep-Pickle an König senden."""
    path = Path(local_path)
    if not path.is_file():
        return {"ok": False, "message_de": "Artifact fehlt lokal"}
    token = str(join_token or "").strip()
    if not token:
        return {"ok": False, "message_de": "join_token fehlt"}
    hub = str(hub_url or "").rstrip("/")
    data = path.read_bytes()
    req = urllib.request.Request(
        f"{hub}/api/h1/artifact/upload",
        data=data,
        headers={
            "Content-Type": "application/octet-stream",
            "X-AA-Join-Token": token,
            "X-AA-Chunk-Id": str(chunk_id or path.stem),
            "X-AA-Worker-Id": str(worker_id or ""),
            "X-AA-Run-Dir": str(run_dir or ""),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        doc = json.loads(raw) if raw.strip() else {}
        return doc if isinstance(doc, dict) else {"ok": False, "message_de": "Ungültige Antwort"}
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            doc = json.loads(raw) if raw.strip() else {}
            if isinstance(doc, dict) and doc.get("message_de"):
                return {"ok": False, **doc}
        except Exception:
            pass
        return {"ok": False, "message_de": f"Upload HTTP {exc.code}"}
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError) as exc:
        return {"ok": False, "message_de": str(exc)[:200]}


def should_sync_assets(hub_url: str, root: Path, features_path: Path) -> bool:
    if features_path.is_file() and features_path.stat().st_size > 0:
        return False
    if not str(hub_url or "").strip():
        return False
    from analytics.preview_federation import is_federation_king

    return not is_federation_king(root) or _is_remote_hub(hub_url)


def should_upload_artifact(hub_url: str, root: Path) -> bool:
    if not str(hub_url or "").strip():
        return False
    from analytics.preview_federation import is_federation_king

    if not is_federation_king(root):
        return True
    return _is_remote_hub(hub_url)
