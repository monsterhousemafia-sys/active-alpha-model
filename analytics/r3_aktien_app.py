"""R3 Aktien-App — nur DAILY_ALPHA_H1 (bestes Modell), kein Profil-Mix."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

_CONFIG_REL = Path("control/r3_aktien_app.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_aktien_config(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _CONFIG_REL)
    if doc:
        return doc
    return {
        "allowed_profile": "daily_alpha_h1",
        "allowed_variant": "DAILY_ALPHA_H1",
        "label_de": "Aktien",
    }


def model_policy(root: Path) -> Dict[str, Any]:
    """Prüft, ob nur das autorisierte Bestmodell aktiv ist."""
    root = Path(root)
    cfg = load_aktien_config(root)
    allowed_profile = str(cfg.get("allowed_profile") or "daily_alpha_h1")
    allowed_variant = str(cfg.get("allowed_variant") or "DAILY_ALPHA_H1")

    active_profile = allowed_profile
    active_variant = allowed_variant
    try:
        from analytics.prediction_operations import active_profile as _active_profile
        from analytics.prediction_operations import profile_variant_key

        active_profile = _active_profile(root)
        active_variant = profile_variant_key(root, active_profile)
    except Exception:
        pass

    ops = _load_json(root / "control/prediction_operations.json")
    strategic = ops.get("strategic_model") or {}
    tier2_variant = str(strategic.get("tier_2_live_signal_variant") or allowed_variant)

    ok = active_profile == allowed_profile and active_variant == allowed_variant
    return {
        "ok": ok,
        "allowed_profile": allowed_profile,
        "allowed_variant": allowed_variant,
        "active_profile": active_profile,
        "active_variant": active_variant,
        "tier_2_variant": tier2_variant,
        "model_label_de": allowed_variant,
        "message_de": (
            f"{allowed_variant} aktiv"
            if ok
            else f"Nur {allowed_variant} erlaubt — aktiv: {active_variant or active_profile}"
        ),
    }


def build_aktien_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_aktien_config(root)
    pol = model_policy(root)
    readiness = _load_json(root / "control/prediction_readiness.json")
    h1 = _load_json(root / "control/h1_governance_status.json")
    return {
        "aktien_app_id": cfg.get("id") or "aktien",
        "aktien_label_de": cfg.get("label_de") or "Aktien",
        "aktien_detail_de": cfg.get("detail_de"),
        "aktien_model_de": pol.get("model_label_de"),
        "aktien_model_ok": pol.get("ok"),
        "aktien_model_message_de": pol.get("message_de"),
        "aktien_disclaimer_de": cfg.get("disclaimer_de"),
        "aktien_h1_sealed": bool(h1.get("sealed")) or str(h1.get("status") or "").upper() == "SEALED",
        "aktien_readiness_ok": readiness.get("ok"),
    }


def launch_aktien_app(root: Path) -> Dict[str, Any]:
    """Order-Desk nur mit DAILY_ALPHA_H1 — andere Profile werden abgelehnt."""
    root = Path(root).resolve()
    cfg = load_aktien_config(root)
    pol = model_policy(root)

    if not pol.get("ok"):
        return {
            "ok": False,
            "feature_id": "aktien",
            "error_de": pol.get("message_de") or "Nur DAILY_ALPHA_H1 ist für die Aktien-App freigegeben.",
        }

    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return {"ok": False, "error_de": "Keine grafische Sitzung — Aktien-App nur am Desktop."}

    launcher = root / str(cfg.get("launcher_rel") or "run_marktanalyse_linux.sh")
    if not launcher.is_file():
        return {"ok": False, "error_de": "Order-Desk Launcher fehlt."}

    env = os.environ.copy()
    env["AA_PROJECT_ROOT"] = str(root)
    env["AA_LINUX_NATIVE_APP"] = "1"
    env["AA_PREDICTION_PROFILE"] = str(pol.get("allowed_profile"))
    env["AA_VARIANT_ID"] = str(pol.get("allowed_variant"))
    env["AA_AKTIEN_APP_ONLY"] = str(pol.get("allowed_variant"))

    try:
        from analytics.prediction_operations import apply_prediction_profile_to_env

        env.update(apply_prediction_profile_to_env(root, env))
        env["AA_PREDICTION_PROFILE"] = str(pol.get("allowed_profile"))
        env["AA_VARIANT_ID"] = str(pol.get("allowed_variant"))
    except Exception:
        pass

    try:
        subprocess.Popen(
            [str(launcher)],
            cwd=str(root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        label = str(cfg.get("label_de") or "Aktien")
        model = str(pol.get("allowed_variant"))
        return {
            "ok": True,
            "feature_id": "aktien",
            "label_de": label,
            "model_de": model,
            "message_de": f"{label} öffnet — nur {model}.",
        }
    except OSError as exc:
        return {"ok": False, "error_de": str(exc)[:200]}
