"""König 32B — Forschungsprojekt-Bestandteil."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.king_32b_forschung import (
    FORSCHUNG_COMPONENT_ID,
    FORSCHUNG_SYSTEM_IDENTITY_DE,
    build_king_32b_forschung_status,
    is_forschungsprojekt_component,
    load_forschungsprojekt_policy,
    resolve_growth_phase,
)


def test_policy_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    pol = load_forschungsprojekt_policy(root)
    assert pol.get("component_id") == FORSCHUNG_COMPONENT_ID
    assert "qwen2.5-coder:32b" in str(pol.get("model"))


def test_is_forschungs_component() -> None:
    assert is_forschungsprojekt_component("king_32b_forschung")
    assert is_forschungsprojekt_component("alpha-model-agent")
    assert not is_forschungsprojekt_component("random")


def test_growth_phase_keim_without_ollama(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/king_32b_forschungsprojekt.json").write_text("{}", encoding="utf-8")
    g = resolve_growth_phase(tmp_path)
    assert g.get("phase") == "keim"
    assert g.get("next_growth_de")


def test_build_status_persists(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    pol = root / "control/king_32b_forschungsprojekt.json"
    if pol.is_file():
        (tmp_path / "control").mkdir(parents=True, exist_ok=True)
        (tmp_path / "control/king_32b_forschungsprojekt.json").write_text(
            pol.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    doc = build_king_32b_forschung_status(tmp_path, persist=True)
    assert doc.get("is_forschungsprojekt") is True
    assert (tmp_path / "evidence/king_32b_forschung_latest.json").is_file()


def test_system_identity_mentions_forschung() -> None:
    assert "Forschungsprojekt" in FORSCHUNG_SYSTEM_IDENTITY_DE
    assert "wächst" in FORSCHUNG_SYSTEM_IDENTITY_DE.lower()


def test_forschungszweig_includes_king_32b() -> None:
    root = Path(__file__).resolve().parents[1]
    from analytics.r3_forschungszweig import build_forschungszweig_status

    doc = build_forschungszweig_status(root)
    k32 = doc.get("king_32b_forschung") or {}
    assert k32.get("is_forschungsprojekt") is True
