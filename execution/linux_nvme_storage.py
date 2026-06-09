"""NVMe fast-data tier for native Linux pilot (archives + shared caches)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

_CONFIG_REL = Path("control/linux_nvme_storage.json")


def _load_config(root: Path) -> Dict[str, Any]:
    path = Path(root) / _CONFIG_REL
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_nvme_mount(root: Path) -> Optional[Path]:
    cfg = _load_config(root)
    if not cfg.get("enabled", True):
        return None
    for raw in cfg.get("mount_candidates") or []:
        mount = Path(str(raw))
        if mount.is_dir() and os.access(mount, os.W_OK | os.R_OK):
            return mount
    media = Path("/run/media") / (os.environ.get("USER") or "machinax7")
    if media.is_dir():
        for child in sorted(media.iterdir()):
            if child.is_dir() and os.access(child, os.W_OK | os.R_OK):
                return child
    return None


def nvme_data_root(root: Path) -> Optional[Path]:
    mount = resolve_nvme_mount(root)
    if mount is None:
        return None
    sub = str(_load_config(root).get("data_subdir") or "active_alpha_fast_data")
    return mount / sub


def shared_cache_dir(root: Path) -> Optional[Path]:
    data = nvme_data_root(root)
    if data is None:
        return None
    sub = str(_load_config(root).get("shared_cache_subdir") or "shared_cache")
    return data / sub


def migrate_dir_names(root: Path) -> List[str]:
    return [str(x) for x in (_load_config(root).get("migrate_dirs") or []) if str(x).strip()]


def _symlink_broken(path: Path) -> bool:
    return path.is_symlink() and not path.exists()


def repair_migrated_symlinks(root: Path) -> Dict[str, Any]:
    """Relink NVMe symlinks when mounted; local fallback dirs when drive is offline."""
    root = Path(root)
    mount = resolve_nvme_mount(root)
    data = nvme_data_root(root)
    repaired: List[Dict[str, Any]] = []
    for name in migrate_dir_names(root):
        path = root / name
        if not _symlink_broken(path):
            continue
        try:
            path.unlink()
        except OSError:
            repaired.append({"name": name, "action": "unlink_failed"})
            continue
        nvme_path = (data / name) if data else None
        if mount is not None and nvme_path is not None and nvme_path.exists():
            path.symlink_to(nvme_path)
            repaired.append({"name": name, "action": "relinked", "target": str(nvme_path)})
        else:
            path.mkdir(parents=True, exist_ok=True)
            repaired.append(
                {
                    "name": name,
                    "action": "local_fallback",
                    "note_de": "NVMe offline — lokales Verzeichnis bis SSD eingehängt",
                }
            )
    return {
        "mount": str(mount) if mount else None,
        "data_root": str(data) if data else None,
        "repaired": repaired,
        "ok": True,
    }


def apply_nvme_storage_env(root: Path) -> Dict[str, str]:
    """Set cache/temp env when NVMe tier is available (no-op on missing mount)."""
    return apply_nvme_constant_storage(root, priority_only=False)


def apply_nvme_constant_storage(
    root: Path,
    *,
    priority_only: bool = False,
) -> Dict[str, str]:
    """
    NVMe als konstanter Hochprioritäts-Speicher — Caches, Kernel-Store, Scratch.
    Wird bei jedem nativen Kernel-/König-Start angewendet.
    """
    root = Path(root)
    repair_migrated_symlinks(root)
    cfg = _load_config(root)
    const_cfg = cfg.get("constant_storage") or {}
    priority = str(const_cfg.get("priority") or "high").lower()
    applied: Dict[str, str] = {}

    cache = shared_cache_dir(root)
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)
        os.environ["AA_SHARED_CACHE_DIR"] = str(cache)
        applied["AA_SHARED_CACHE_DIR"] = str(cache)

    data = nvme_data_root(root)
    if data is not None:
        os.environ["AA_NVME_DATA_ROOT"] = str(data)
        applied["AA_NVME_DATA_ROOT"] = str(data)
        if priority == "high":
            os.environ["AA_NVME_PRIORITY"] = "high"
            applied["AA_NVME_PRIORITY"] = "high"

        env_dirs = const_cfg.get("env_dirs") or {}
        for env_key, subdir in env_dirs.items():
            path = data / str(subdir)
            path.mkdir(parents=True, exist_ok=True)
            os.environ[str(env_key)] = str(path)
            applied[str(env_key)] = str(path)

        tmp_sub = str(const_cfg.get("tmpdir_subdir") or "tmp")
        tmp_path = data / tmp_sub
        tmp_path.mkdir(parents=True, exist_ok=True)
        os.environ["TMPDIR"] = str(tmp_path)
        applied["TMPDIR"] = str(tmp_path)

        if not priority_only:
            scratch = data / str(const_cfg.get("scratch_subdir") or "scratch")
            scratch.mkdir(parents=True, exist_ok=True)
            os.environ["AA_NVME_SCRATCH"] = str(scratch)
            applied["AA_NVME_SCRATCH"] = str(scratch)

    return applied


def storage_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = _load_config(root)
    mount = resolve_nvme_mount(root)
    data = nvme_data_root(root)
    cache = shared_cache_dir(root)
    migrated: List[Dict[str, Any]] = []
    for name in migrate_dir_names(root):
        path = root / name
        migrated.append(
            {
                "name": name,
                "symlink": path.is_symlink(),
                "target": str(path.resolve()) if path.exists() else None,
                "on_nvme": str(path.resolve()).startswith(str(mount)) if mount and path.exists() else False,
            }
        )
    free_gb = None
    if mount is not None:
        try:
            stat = os.statvfs(mount)
            free_gb = round((stat.f_bavail * stat.f_frsize) / (1024**3), 1)
        except OSError:
            pass
    const_cfg = cfg.get("constant_storage") or {}
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "mount": str(mount) if mount else None,
        "data_root": str(data) if data else None,
        "shared_cache": str(cache) if cache else None,
        "constant_storage_priority": str(const_cfg.get("priority") or "high"),
        "constant_storage_active": bool(mount and data),
        "free_gb": free_gb,
        "migrated_dirs": migrated,
        "env": {
            "AA_SHARED_CACHE_DIR": os.environ.get("AA_SHARED_CACHE_DIR", ""),
            "AA_NVME_DATA_ROOT": os.environ.get("AA_NVME_DATA_ROOT", ""),
            "AA_NVME_PRIORITY": os.environ.get("AA_NVME_PRIORITY", ""),
            "AA_KERNEL_STORE": os.environ.get("AA_KERNEL_STORE", ""),
            "TMPDIR": os.environ.get("TMPDIR", ""),
        },
    }
