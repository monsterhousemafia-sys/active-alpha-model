"""Local LLM bridge — Ollama chat with Active Alpha project context (Stufe 3)."""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_CONFIG_REL = Path("control/local_llm.json")


def load_llm_config(root: Path) -> Dict[str, Any]:
    path = Path(root) / _CONFIG_REL
    if not path.is_file():
        return {
            "provider": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "default_model": "qwen2.5:7b",
            "system_prompt_de": "Du bist Auto, lokaler Active-Alpha-Operator.",
            "temperature": 0.4,
        }
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def ollama_available(base_url: str, *, timeout_s: float = 3.0) -> bool:
    try:
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status == 200
    except Exception:
        return False


def ensure_ollama_running(root: Path) -> Dict[str, Any]:
    """Ollama erreichbar machen — systemctl oder ollama serve (kein Modell-Pull)."""
    root = Path(root)
    cfg = load_llm_config(root)
    base = str(cfg.get("base_url") or "http://127.0.0.1:11434")
    if ollama_available(base, timeout_s=1.5):
        return {"ok": True, "base_url": base, "started": False, "detail_de": base}

    started_via = None
    try:
        proc = subprocess.run(
            ["systemctl", "start", "ollama"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if proc.returncode == 0:
            started_via = "systemctl"
            time.sleep(2.0)
            if ollama_available(base, timeout_s=3.0):
                return {
                    "ok": True,
                    "base_url": base,
                    "started": True,
                    "method": started_via,
                    "detail_de": base,
                }
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        started_via = "ollama serve"
        for _ in range(6):
            time.sleep(0.5)
            if ollama_available(base, timeout_s=2.0):
                return {
                    "ok": True,
                    "base_url": base,
                    "started": True,
                    "method": started_via,
                    "detail_de": base,
                }
    except (FileNotFoundError, OSError) as exc:
        return {
            "ok": False,
            "base_url": base,
            "started": False,
            "detail_de": f"Ollama fehlt — bash tools/setup_local_llm.sh ({exc})"[:120],
        }

    return {
        "ok": False,
        "base_url": base,
        "started": bool(started_via),
        "method": started_via,
        "detail_de": "Ollama nicht erreichbar — bash tools/setup_local_llm.sh",
    }


def list_ollama_models(base_url: str) -> List[str]:
    try:
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        return [str(m.get("name") or "") for m in (doc.get("models") or []) if m.get("name")]
    except Exception:
        return []


def resolve_model_options(cfg: Dict[str, Any], model: str) -> Dict[str, Any]:
    opts = (cfg.get("role_model_options") or {}).get(str(model or "")) or {}
    num_ctx = int(opts.get("num_ctx") or cfg.get("default_num_ctx") or 8192)
    return {"num_ctx": num_ctx, "note_de": opts.get("note_de")}


def resolve_model(root: Path, cfg: Optional[Dict[str, Any]] = None, *, role: Optional[str] = None) -> str:
    if role:
        try:
            from analytics.r3_model_synergy import resolve_ollama_role

            return str(resolve_ollama_role(root, "", mode=role).get("model") or "")
        except Exception:
            pass
    cfg = cfg or load_llm_config(root)
    base = str(cfg.get("base_url") or "http://127.0.0.1:11434")
    preferred = str(cfg.get("default_model") or "qwen2.5:7b")
    installed = list_ollama_models(base)
    if not installed:
        return preferred
    if preferred in installed:
        return preferred
    for fb in cfg.get("fallback_models") or []:
        if fb in installed:
            return str(fb)
    return installed[0]


def _context_file_list(cfg: Dict[str, Any]) -> List[str]:
    try:
        from analytics.alpha_model_king_control import is_king_control_active

        if is_king_control_active():
            king_files = list(cfg.get("context_files_king") or [])
            if king_files:
                return king_files
    except Exception:
        pass
    return list(cfg.get("context_files") or [])


def build_project_context(root: Path, cfg: Optional[Dict[str, Any]] = None) -> str:
    cfg = cfg or load_llm_config(root)
    root = Path(root)
    max_chars = int(cfg.get("max_context_chars") or 12000)
    chunks: List[str] = []
    for rel in _context_file_list(cfg):
        path = root / str(rel)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.suffix == ".json":
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=0)[:3000]
            chunks.append(f"--- {rel} ---\n{text[:3000]}")
        except Exception:
            continue
    try:
        from analytics.operator_visibility import build_visibility_snapshot, format_visibility_text

        vis = format_visibility_text(build_visibility_snapshot(root))
        chunks.append(f"--- operator_visibility ---\n{vis[:2500]}")
    except Exception:
        pass
    body = "\n\n".join(chunks)
    return body[:max_chars]


def chat_completion(
    root: Path,
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    stream: bool = False,
    timeout_s: float = 300.0,
    temperature: Optional[float] = None,
    num_ctx: Optional[int] = None,
    role: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    cfg = load_llm_config(root)
    base = str(cfg.get("base_url") or "http://127.0.0.1:11434")
    if role and not model:
        try:
            from analytics.r3_model_synergy import resolve_ollama_role

            pick = resolve_ollama_role(root, "", mode=role)
            model = str(pick.get("model") or "") or None
            if num_ctx is None and pick.get("num_ctx"):
                num_ctx = int(pick["num_ctx"])
        except Exception:
            pass
    model = model or resolve_model(root, cfg)
    temp = float(temperature if temperature is not None else cfg.get("temperature") or 0.4)
    ctx = int(num_ctx if num_ctx is not None else resolve_model_options(cfg, model).get("num_ctx") or 8192)
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": {"temperature": temp, "num_ctx": ctx},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=float(timeout_s)) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Ollama HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            "Ollama nicht erreichbar — bash tools/setup_local_llm.sh ausführen"
        ) from exc
    content = str((doc.get("message") or {}).get("content") or "")
    return content, doc


def run_kernel_command(root: Path, command: str) -> str:
    """Execute whitelisted ai_kernel subcommand and return stdout."""
    allowed = {
        "status", "warnings", "learn", "evolve", "visibility", "scope",
        "h1-status", "ready", "maintain", "monday-prep", "audit",
        "refresh", "trading-day", "circle", "gui-preview", "llm-health", "h1-watch", "h1-finish",
        "runtime-install", "runtime-status", "runtime-watch", "runtime-query",
        "r3-preserve", "human-interface", "agent-home", "r3-migration-check",
        "r3-build", "build-kernel",
    }
    if os.environ.get("AA_AGENT_CHAMBER", "").strip() in ("1", "true", "yes"):
        try:
            from analytics.alpha_model_chamber_resources import chamber_kernel_allowlist

            allowed = set(chamber_kernel_allowlist(root)) or allowed
        except Exception:
            pass
    parts = command.strip().split()
    cmd = parts[0] if parts else ""
    if cmd not in allowed:
        return f"Unbekannter Befehl: {cmd}. Erlaubt: {', '.join(sorted(allowed))}"
    import subprocess
    import sys

    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(sys.executable)
    timeout_s = 120.0
    if cmd.startswith("king-") or cmd in {"h1-benchmark", "h1-watch", "h1-connect", "king-distribute", "king-pulse"}:
        timeout_s = 7200.0
    proc = subprocess.run(
        [str(py), "tools/ai_kernel.py", *parts],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return out[-8000:] if out else f"(exit {proc.returncode}, keine Ausgabe)"


def initial_messages(root: Path) -> List[Dict[str, str]]:
    cfg = load_llm_config(root)
    ctx = build_project_context(root, cfg)
    system = str(cfg.get("system_prompt_de") or "")
    try:
        from analytics.alpha_model_agent_home import build_agent_chamber_prompt, is_agent_chamber_active

        if is_agent_chamber_active():
            system = build_agent_chamber_prompt(root)
    except Exception:
        pass
    king_lean = False
    try:
        from analytics.alpha_model_king_control import is_king_control_active

        king_lean = is_king_control_active()
    except Exception:
        pass
    if ctx:
        system += "\n\nEvidence-Kontext:\n" + ctx
    if king_lean:
        system += (
            "\n\nNetzwerk: control/king_network.json · Pulse: evidence/king_network_pulse_latest.json"
            "\nSchichten: 1=Bash · 2=Python · 3=Du · 4=Cursor — Takt: phase + beat + handoff_to"
            "\nStart: bash tools/king_ops.sh network → Takt lesen → king_ops befehlen"
            "\nSlash: /tune /pipeline /king-status /könig-puls /hilfe /quit"
        )
    else:
        system += (
            "\n\nSlash: /status /learn /h1-benchmark /h1-watch /bau /hilfe /quit"
            "\nBash: bash tools/setup_ideal_32b.sh"
        )
    if not king_lean:
        try:
            from analytics.r3_conversation_continuity import load_continuity_context

            cont = load_continuity_context(root)
            if cont:
                system += "\n\nGesprächskontinuität:\n" + cont[:4000]
        except Exception:
            pass
    return [{"role": "system", "content": system}]


def warmup_ollama(root: Path, *, timeout_s: float = 8.0) -> bool:
    """Best-effort ping before Preview-Chat (Cold-Start nach Boot)."""
    cfg = load_llm_config(root)
    base = str(cfg.get("base_url") or "http://127.0.0.1:11434")
    return ollama_available(base, timeout_s=timeout_s)


def health_report(root: Path) -> Dict[str, Any]:
    cfg = load_llm_config(root)
    base = str(cfg.get("base_url") or "http://127.0.0.1:11434")
    ok = ollama_available(base)
    models = list_ollama_models(base) if ok else []
    model = resolve_model(root, cfg) if ok else cfg.get("default_model")
    if ok and os.environ.get("AA_AGENT_CHAMBER", "").strip() in ("1", "true", "yes"):
        try:
            chat_model = str(resolve_model(root, cfg, role="chat") or "")
            if chat_model:
                model = chat_model
        except Exception:
            pass
    role_status: Dict[str, Any] = {}
    try:
        from analytics.r3_model_synergy import resolve_ollama_role

        picks = {
            "chat": resolve_ollama_role(root, "", mode="chat"),
            "build": resolve_ollama_role(root, "", mode="build"),
            "trading_local": resolve_ollama_role(root, "trading h1 signal alpha", mode="chat"),
        }
        for mode, pick in picks.items():
            role_status[mode] = {
                "model": pick.get("model"),
                "preferred": pick.get("preferred"),
                "num_ctx": pick.get("num_ctx"),
                "installed": pick.get("model") in models if pick.get("model") else False,
            }
    except Exception:
        pass
    pull_models = list(cfg.get("pull_models") or [])
    missing = [m for m in pull_models if m not in models] if pull_models else []
    return {
        "ollama_ok": ok,
        "base_url": base,
        "default_model": cfg.get("default_model"),
        "resolved_model": model,
        "installed_models": models,
        "gpu_tier_de": cfg.get("gpu_tier_de"),
        "role_models": cfg.get("role_models"),
        "role_status": role_status,
        "pull_models_missing": missing,
        "stage": cfg.get("stage", 3),
        "ready": ok and bool(models),
        "max_tier_ready": ok and not missing if pull_models else ok and bool(models),
    }
