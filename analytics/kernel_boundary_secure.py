"""Abgesicherter Kernel-Grenz-Pfad — Audit & Whitelist, kein Kernel-Tausch."""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/kernel_boundary_policy.json")
_EVIDENCE_REL = Path("evidence/kernel_boundary_audit_latest.json")
_APPLY_ACK_REL = Path("evidence/kernel_boundary_apply_ack.json")
_SYSCTL_ACK_REL = Path("evidence/kernel_boundary_sysctl_ack.json")

_FORBIDDEN_PATTERNS = (
    r"make\s+.*\b(kernel|bzImage|modules)\b",
    r"\b(insmod|modprobe)\s+",
    r"/boot/vmlinuz",
    r"\bupdate-grub\b",
    r"\bdracut\b",
    r"\bmkinitramfs\b",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_policy(root: Path) -> Dict[str, Any]:
    path = Path(root) / _POLICY_REL
    if not path.is_file():
        return {"schema_version": 1, "forbidden_always_de": [], "sysctl_whitelist": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def is_forbidden_command(cmd: str) -> Tuple[bool, str]:
    text = str(cmd or "").strip()
    if not text:
        return False, ""
    for pat in _FORBIDDEN_PATTERNS:
        if re.search(pat, text, re.I):
            return True, pat
    return False, ""


def _run(args: List[str], *, timeout: float = 4.0) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        out = (proc.stdout or proc.stderr or "").strip()
        return proc.returncode, out[:4000]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)[:300]


def _read_sysctl(keys: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in keys:
        path = Path("/proc/sys") / key.replace(".", "/")
        if path.is_file():
            try:
                out[key] = path.read_text(encoding="utf-8").strip()
            except OSError:
                out[key] = None
    return out


def _nvme_scheduler() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    block = Path("/sys/block")
    if not block.is_dir():
        return rows
    for dev in sorted(block.iterdir()):
        if not dev.name.startswith("nvme"):
            continue
        sched = dev / "queue" / "scheduler"
        if sched.is_file():
            try:
                rows.append({"device": dev.name, "scheduler": sched.read_text(encoding="utf-8").strip()})
            except OSError:
                pass
    return rows


def audit_kernel_boundary(root: Path) -> Dict[str, Any]:
    """L0 — nur lesen, keine Änderungen am Kernel."""
    root = Path(root)
    policy = load_policy(root)

    _, uname = _run(["uname", "-srvm"])
    _, modules_head = _run(["lsmod"])
    modules = [ln.split()[0] for ln in modules_head.splitlines()[1:6] if ln.strip()]

    whitelist = list((policy.get("sysctl_whitelist") or {}).keys())
    sysctl = _read_sysctl(whitelist)

    limits: Dict[str, Any] = {}
    try:
        import resource

        limits["nofile_soft"], limits["nofile_hard"] = resource.getrlimit(resource.RLIMIT_NOFILE)
    except Exception:
        pass

    runtime_installed = (root / "evidence/aa_linux_runtime_latest.json").is_file()

    recommendations: List[str] = []
    try:
        nofile = int(limits.get("nofile_soft") or 0)
        if nofile < 65536:
            recommendations.append(
                "FD-Limit niedrig — ai_kernel runtime-install (systemd LimitNOFILE) statt Kernel-Build"
            )
    except (TypeError, ValueError):
        pass
    if not runtime_installed:
        recommendations.append("Runtime-Schicht fehlt — ai_kernel runtime-install (Kernel-Ersatz auf Userspace-Ebene)")
    try:
        swappiness = int(sysctl.get("vm.swappiness") or 60)
        if swappiness > 40:
            recommendations.append(
                "vm.swappiness hoch — optional Level-D sysctl nach Operator-Ack (kein eigener Kernel)"
            )
    except (TypeError, ValueError):
        pass

    doc = {
        "schema_version": 1,
        "audited_at_utc": _utc_now(),
        "kernel": {
            "uname": uname,
            "modules_sample": modules,
            "replacement_forbidden": True,
        },
        "nvme_schedulers": _nvme_scheduler(),
        "sysctl_whitelist_read": sysctl,
        "process_limits": limits,
        "runtime_layer_installed": runtime_installed,
        "forbidden_always_de": policy.get("forbidden_always_de") or [],
        "secure_path_de": policy.get("secure_path_de"),
        "recommendations_de": recommendations,
        "headline_de": "Kernel-Grenze auditiert — Mainline bleibt, Runtime + Whitelist-Tuning",
        "ok": True,
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    try:
        from analytics.linux_operator_scope import log_operator_action

        log_operator_action(root, level="A", action="kernel_boundary_audit", result="OK")
    except Exception:
        pass
    return doc


def _ack_ok(root: Path, rel: Path) -> bool:
    path = Path(root) / rel
    if not path.is_file():
        return False
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return bool(doc.get("ok"))
    except (json.JSONDecodeError, OSError):
        return False


def apply_secure_userspace_layer(root: Path, *, dry_run: bool = True) -> Dict[str, Any]:
    """L1/L2 — Runtime installieren, nie Kernel anfassen."""
    root = Path(root)
    from analytics.linux_operator_scope import level_allowed, log_operator_action

    if not level_allowed(root, "B"):
        return {
            "ok": False,
            "blocked_de": "Operator-Level B nicht freigegeben — nur Audit (kernel-boundary)",
        }
    if not dry_run and not _ack_ok(root, _APPLY_ACK_REL):
        return {
            "ok": False,
            "blocked_de": "Apply-Ack fehlt — evidence/kernel_boundary_apply_ack.json mit ok:true",
            "hint_de": "ai_kernel kernel-boundary --ack-apply",
        }

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "would_run": ["runtime-install"],
            "detail_de": "Dry-run — --apply nach --ack-apply",
        }

    from analytics.aa_linux_runtime import install_linux_runtime

    runtime = install_linux_runtime(root, enable=True)
    log_operator_action(root, level="B", action="kernel_boundary_apply_runtime", result="OK")
    return {"ok": True, "dry_run": False, "runtime": runtime}


def plan_sysctl_changes(root: Path) -> Dict[str, Any]:
    """L3 — nur Plan, Apply nur manuell mit root + Ack."""
    root = Path(root)
    policy = load_policy(root)
    audit = audit_kernel_boundary(root)
    current = audit.get("sysctl_whitelist_read") or {}
    whitelist = policy.get("sysctl_whitelist") or {}
    planned: List[Dict[str, Any]] = []

    for key, spec in whitelist.items():
        if not isinstance(spec, dict):
            continue
        cur_raw = current.get(key)
        try:
            cur = int(str(cur_raw).strip())
        except (TypeError, ValueError):
            cur = None
        target = int(spec.get("max", cur or 0))
        if cur is not None and cur >= target:
            continue
        planned.append(
            {
                "key": key,
                "current": cur_raw,
                "suggested": target,
                "reason_de": spec.get("reason_de"),
                "apply_de": f"sudo sysctl -w {key}={target}",
                "operator_only": True,
            }
        )

    return {
        "schema_version": 1,
        "planned_at_utc": _utc_now(),
        "changes": planned,
        "ack_required": str(_SYSCTL_ACK_REL),
        "autonomous_apply": False,
        "headline_de": "sysctl-Plan — nie automatisch, nur Operator mit sudo",
    }


def write_apply_ack(root: Path, *, detail_de: str = "Userspace-Runtime Apply freigegeben") -> Dict[str, Any]:
    doc = {
        "schema_version": 1,
        "ok": True,
        "ack_at_utc": _utc_now(),
        "detail_de": detail_de,
        "forbidden_de": "Kein Kernel-Image-Tausch — nur Runtime-Schicht",
    }
    atomic_write_json(Path(root) / _APPLY_ACK_REL, doc)
    return doc


def run_kernel_boundary(
    root: Path,
    *,
    mode: str = "audit",
    dry_run: bool = True,
) -> Dict[str, Any]:
    root = Path(root)
    mode = str(mode or "audit").strip().lower()

    if mode == "audit":
        return audit_kernel_boundary(root)
    if mode == "plan-sysctl":
        audit_kernel_boundary(root)
        return plan_sysctl_changes(root)
    if mode == "apply-runtime":
        return apply_secure_userspace_layer(root, dry_run=dry_run)
    if mode == "guard":
        cmd = os.environ.get("AA_GUARD_CMD", "")
        bad, pat = is_forbidden_command(cmd)
        return {
            "ok": not bad,
            "cmd": cmd,
            "blocked": bad,
            "pattern": pat if bad else None,
            "detail_de": "Verboten" if bad else "Erlaubt",
        }
    return {"ok": False, "error_de": f"unbekannter Modus: {mode}"}
