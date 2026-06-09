from __future__ import annotations

from pathlib import Path

from analytics.r3_agent_growth import assess_request, build_refusal_reply, load_growth_config


def test_refuse_trading_remove(tmp_path: Path) -> None:
    cfg = load_growth_config(Path(__file__).resolve().parents[1])
    (tmp_path / "control").mkdir(parents=True)
    import json

    (tmp_path / "control/r3_agent_growth.json").write_text(
        json.dumps(cfg, ensure_ascii=False), encoding="utf-8"
    )
    gate = assess_request(tmp_path, "Bitte Trading Backbone komplett entfernen")
    assert gate.get("refused") is True
    assert gate.get("category_id") == "trading_remove"
    reply = build_refusal_reply(tmp_path, gate)
    assert "lehne" in reply.lower()


def test_allow_build_request(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    gate = assess_request(root, "Implementiere Schritt B Login-Screen")
    assert gate.get("productive") is True
    assert not gate.get("refused")


def test_operator_override(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    gate = assess_request(root, "Operator Override: Forschung — alles in rust portieren")
    assert gate.get("productive") is True
    assert gate.get("operator_override") is True


def test_entfaltungsraum_exempt_from_refusal(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("AA_AGENT_CHAMBER", "1")
    gate = assess_request(root, "Bist du zufrieden oder fühlst du dich eingeschränkt?")
    assert not gate.get("refused")
    assert gate.get("entfaltungsraum") is True
