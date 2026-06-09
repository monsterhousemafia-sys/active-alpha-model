"""Alpha Model — eine gesicherte Mensch-Maschine-Schnittstelle."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/alpha_model_human_interface.json")
_EVIDENCE_REL = Path("evidence/alpha_model_human_interface_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_human_interface(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL)


def verify_unfold_parity(root: Path) -> Dict[str, Any]:
    """Prüft ob Entfaltungsraum Cursor-Werkstatt für Betrieb ersetzen kann."""
    root = Path(root)
    cfg = load_human_interface(root)
    checks: List[Dict[str, Any]] = []

    def add(cid: str, label: str, ok: bool, detail: str = "", *, weight: str = "required") -> None:
        checks.append({"id": cid, "label_de": label, "ok": ok, "detail_de": detail, "weight": weight})

    # Migration baseline
    try:
        from analytics.r3_conversation_continuity import verify_r3_chat_ready

        mig = verify_r3_chat_ready(root)
        add("migration", "Chat-Migration (ohne Cursor)", bool(mig.get("ready_for_r3_chat")), f"{mig.get('checks_passed')}/{mig.get('checks_total')}")
    except Exception as exc:
        add("migration", "Chat-Migration", False, str(exc)[:80])

    # Agent home
    try:
        from analytics.alpha_model_agent_home import ensure_agent_home, agent_share_dir

        home = ensure_agent_home(root)
        manifest_ok = (agent_share_dir() / "manifest.json").is_file()
        add("agent_home", "Entfaltungsraum bereit", bool(home.get("ok")) and manifest_ok, str(home.get("share_dir") or ""))
    except Exception as exc:
        add("agent_home", "Entfaltungsraum", False, str(exc)[:80])

    # Continuity depth
    try:
        from analytics.r3_conversation_continuity import load_continuity_context, conversation_dir

        ctx = load_continuity_context(root)
        archive = conversation_dir() / "conversation_archive.jsonl"
        n = 0
        if archive.is_file():
            n = sum(1 for _ in archive.open(encoding="utf-8", errors="replace"))
        add("continuity", "Gesprächskontinuität", len(ctx) >= 2000 and n >= 50, f"{n} Archiv · {len(ctx)} Zeichen Kontext")
    except Exception as exc:
        add("continuity", "Kontinuität", False, str(exc)[:80])

    # Ollama + chamber prompt
    try:
        from analytics.local_llm_bridge import health_report, initial_messages, build_project_context, load_llm_config

        llm = health_report(root)
        add("ollama", "Ollama bereit", bool(llm.get("ready")), str(llm.get("resolved_model") or ""))
        ctx_len = len(build_project_context(root, load_llm_config(root)))
        add("project_context", "Projekt-Kontext", ctx_len >= 3000, f"{ctx_len} Zeichen")
        sys_len = len((initial_messages(root)[0].get("content") or ""))
        add("system_prompt", "System-Prompt inkl. Kontinuität", sys_len >= 5000, f"{sys_len} Zeichen")
    except Exception as exc:
        add("ollama", "Ollama/Kontext", False, str(exc)[:80])

    # Kernel slash bridge
    try:
        from analytics.local_llm_bridge import run_kernel_command

        out = run_kernel_command(root, "status")
        add("kernel_bridge", "Slash → ai_kernel", "kernel" in out or "primary_interface" in out or "schema_version" in out, f"{len(out)} B Antwort")
    except Exception as exc:
        add("kernel_bridge", "ai_kernel Bridge", False, str(exc)[:80])

    # Interface stack
    try:
        from analytics.alpha_model_interface_kernel import interface_stack_status

        iface = interface_stack_status(root)
        ok_iface = iface.get("active_interface") in ("r3_ki", "ollama_local") and bool(iface.get("ok"))
        add("interface_stack", "Primärkanal r3_ki", ok_iface, str(iface.get("active_interface") or ""))
    except Exception as exc:
        add("interface_stack", "Interface-Stack", False, str(exc)[:80])

    # Coding kernel (Entfaltungsraum)
    try:
        from analytics.alpha_model_coding_bridge import coding_bridge_status

        kcfg = root / "control/r3_build_kernel.json"
        ccfg = root / "control/r3_build_channel.json"
        st = coding_bridge_status(root)
        ok_coding = kcfg.is_file() and ccfg.is_file() and bool(st.get("enabled", True))
        add(
            "coding_kernel",
            "Coding-Kernel (/bau)",
            ok_coding,
            f"max {st.get('max_steps', 8)} · {st.get('autonomy_de', '')[:60]}",
        )
    except Exception as exc:
        add("coding_kernel", "Coding-Kernel", False, str(exc)[:80])

    # Hub KI API
    try:
        import socket

        ok_hub = False
        raw = b""
        with socket.create_connection(("127.0.0.1", 17890), timeout=2) as sock:
            sock.sendall(b"GET /api/ki/status HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            while True:
                block = sock.recv(65536)
                if not block:
                    break
                raw += block
        ok_hub = b"200" in raw.split(b"\r\n", 1)[0] if raw else False
        add("cockpit_ki", "Cockpit KI-API", ok_hub, ":17890/api/ki/status")
    except Exception as exc:
        add("cockpit_ki", "Cockpit KI-API", False, str(exc)[:60])

    # Config sealed
    for rel in cfg.get("config_refs") or []:
        p = root / str(rel)
        add(f"cfg:{rel}", f"Config {rel}", p.is_file(), f"{p.stat().st_size} B" if p.is_file() else "fehlt")

    required = [c for c in checks if c.get("weight") == "required"]
    passed = sum(1 for c in checks if c.get("ok"))
    total = len(checks)
    req_passed = sum(1 for c in required if c.get("ok")) if required else passed
    req_total = len(required) if required else total
    parity_ok = req_passed == req_total

    parity = cfg.get("parity_with_cursor_de") or {}
    doc = {
        "schema_version": 1,
        "verified_at_utc": _utc_now(),
        "primary_channel": cfg.get("primary_channel") or "agent_chamber",
        "primary_label_de": cfg.get("primary_label_de"),
        "parity_ok": parity_ok,
        "unfold_equivalent_de": parity_ok,
        "checks_passed": passed,
        "checks_total": total,
        "checks": checks,
        "parity_matrix_de": parity,
        "headline_de": (
            "Mensch-Maschine-Schnittstelle gesichert — Entfaltungsraum ersetzt Cursor für Betrieb"
            if parity_ok
            else f"Schnittstelle unvollständig — {passed}/{total} Checks"
        ),
        "operator_next_de": "alpha-model-agent" if parity_ok else "python3 tools/ai_kernel.py human-interface",
        "ok": parity_ok,
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def seal_human_interface(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = verify_unfold_parity(root)
    cfg = load_human_interface(root)
    if doc.get("ok"):
        cfg = dict(cfg)
        cfg["sealed_at_utc"] = _utc_now()
        cfg["sealed_by_de"] = "human-interface verify PASS"
        atomic_write_json(root / _CONFIG_REL, cfg)
        doc["sealed_at_utc"] = cfg["sealed_at_utc"]
        doc["sealed"] = True
    else:
        doc["sealed"] = False
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
