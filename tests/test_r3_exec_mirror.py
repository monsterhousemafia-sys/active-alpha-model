"""R3 Exec Mirror — lokaler Spiegel, nur Ergebnisse."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_mirror_capital import OPERATOR_SYNC_HINT_DE
from analytics.r3_exec_mirror import (
    build_exec_mirror_state,
    display_headline,
    format_stand_de,
    render_r3_exec_mirror_page,
)
from analytics.r3_mirror_state import _resolve_updated_at_utc
from tests.r3_order_fixtures import seed_orders_stack


def test_format_stand_de_europe_berlin() -> None:
    assert format_stand_de("2026-06-08T00:53:00+00:00") == "08.06.2026, 02:53 Uhr (CEST)"


def test_resolve_updated_at_picks_latest() -> None:
    assert (
        _resolve_updated_at_utc(
            {"updated_at_utc": "2026-06-08T00:53:00+00:00"},
            {"updated_at_utc": "2026-06-08T12:00:00+00:00"},
        )
        == "2026-06-08T12:00:00+00:00"
    )


def test_display_headline_strips_zeilen_suffix() -> None:
    assert display_headline("Paket bereit — 641 € · 1 Zeilen") == "Paket bereit — 641 €"


def test_mirror_state_from_evidence(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    bond_path = tmp_path / "evidence/r3_t212_api_bond_latest.json"
    bond = json.loads(bond_path.read_text(encoding="utf-8"))
    bond["confirmation_de"] = "T212 OK"
    bond_path.write_text(json.dumps(bond), encoding="utf-8")
    from analytics.r3_t212_account_identity import confirm_t212_account

    confirm_t212_account(tmp_path, bond=bond)
    (tmp_path / "evidence/r3_freigabe_latest.json").write_text(
        json.dumps(
            {
                "package_ready": True,
                "headline_de": "Paket bereit",
                "prep_steps": [{"step": "t212_bond", "ok": True}],
                "updated_at_utc": "2026-06-08T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    doc = build_exec_mirror_state(tmp_path)
    assert doc.get("t212_connected") is True
    assert doc.get("mirror_de")
    assert "execution_package" in doc
    assert "submission_mode" in doc
    assert "pipeline_layers" in doc
    assert isinstance(doc.get("pipeline_layers"), list)
    assert isinstance(doc.get("system_metrics"), list)


def test_mirror_includes_prognosis_block(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    (tmp_path / "evidence/r3_t212_prognosis_latest.json").write_text(
        json.dumps(
            {
                "ok": True,
                "signal_date": "2026-06-05",
                "investable_eur": 641.0,
                "positions": 2,
                "t212_trusted": True,
                "capital_basis_de": "Live T212 · 641 € investierbar",
                "top_picks": [
                    {"ticker": "STX", "target_weight_pct": 6.0},
                    {"ticker": "MU", "target_weight_pct": 4.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    doc = build_exec_mirror_state(tmp_path)
    prog = doc.get("prognosis") or {}
    assert prog.get("ok") is True
    assert prog.get("positions") == 2
    assert len(prog.get("top_picks") or []) == 2


def test_mirror_page_renders_prognosis_section(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/local_apps_manifest.json").write_text(
        json.dumps({"status": "EXEC_MIRROR_ONLY"}),
        encoding="utf-8",
    )
    seed_orders_stack(tmp_path)
    (tmp_path / "evidence/r3_t212_prognosis_latest.json").write_text(
        json.dumps(
            {
                "ok": True,
                "signal_date": "2026-06-05",
                "investable_eur": 641.0,
                "t212_trusted": True,
                "capital_basis_de": "Live T212",
                "top_picks": [{"ticker": "STX", "target_weight_pct": 6.0}],
            }
        ),
        encoding="utf-8",
    )
    html = render_r3_exec_mirror_page(tmp_path).decode("utf-8")
    assert "r3-mirror-prognosis" not in html
    assert 'class="r3-mirror-empty"' not in html
    assert "r3-freigabe-governance" not in html
    assert 'data-exec-mode="1"' in html


def test_exec_mirror_state_is_lean(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/local_apps_manifest.json").write_text(
        json.dumps({"status": "EXEC_MIRROR_ONLY"}),
        encoding="utf-8",
    )
    seed_orders_stack(tmp_path)
    doc = build_exec_mirror_state(tmp_path)
    assert "pipeline_layers" not in doc
    assert doc.get("voice_warning_de") is None
    assert doc.get("daily_postmortem") == {"bad_day": False}
    assert doc.get("fall_watch") == {"fall_detected": False}


def test_mirror_hides_stale_plan_capital_when_untrusted(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "bonded": True,
                "connected": False,
                "credentials_configured": True,
                "broker_status": "CONNECTION_FAILED_RETRY_AVAILABLE",
                "cash_eur": None,
                "investable_eur": None,
                "last_sync_utc": None,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "investable_eur": 678.52,
                "allocations": [
                    {"symbol": "STX", "target_eur": 339.26, "model_weight_pct": 50.0, "side": "BUY"},
                    {"symbol": "SPY", "target_eur": 339.26, "model_weight_pct": 50.0, "side": "BUY"},
                ],
            }
        ),
        encoding="utf-8",
    )
    doc = build_exec_mirror_state(tmp_path)
    assert doc.get("t212_trusted") is False
    assert doc.get("investable_eur") is None
    mo = doc.get("model_output") or {}
    assert mo.get("investable_eur") is None
    assert mo.get("allocations") == []
    html = render_r3_exec_mirror_page(tmp_path).decode("utf-8")
    assert "678" not in html
    assert "679" not in html
    assert "640" not in html
    assert "nicht vertrauenswürdig" not in html.lower()
    assert "r3-mirror-exec-pkg" not in html
    if doc.get("needs_api_setup"):
        assert "r3-t212-setup" in html
    elif doc.get("credentials_configured"):
        hint = str(doc.get("capital_message_de") or OPERATOR_SYNC_HINT_DE)
        if hint:
            assert hint in html
    pkg = doc.get("execution_package") or {}
    assert pkg.get("notional_eur") == 0.0
    assert pkg.get("lines") == []


def test_mirror_page_no_einzelaktien_grid(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/local_apps_manifest.json").write_text(
        json.dumps({"status": "EXEC_MIRROR_ONLY"}),
        encoding="utf-8",
    )
    seed_orders_stack(tmp_path)
    html = render_r3_exec_mirror_page(tmp_path).decode("utf-8")
    assert 'id="r3-einzel-wrap"' not in html
    assert 'class="r3-stock-btn' not in html


def test_mirror_layers_trace_evidence_fields(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps({"connected": True, "cash_eur": 500.0, "bonded": True}),
        encoding="utf-8",
    )
    doc = build_exec_mirror_state(tmp_path)
    for layer in doc.get("pipeline_layers") or []:
        assert "evidence_ref" in layer
        assert "fields_de" in layer
        assert "value_de" in layer
    for stage in (doc.get("trading_cycle") or {}).get("stages") or []:
        assert stage.get("evidence_ref")
        assert "fields_de" in stage


def test_mirror_page_results_and_exec_button(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/local_apps_manifest.json").write_text(
        json.dumps({"status": "EXEC_MIRROR_ONLY"}),
        encoding="utf-8",
    )
    seed_orders_stack(tmp_path)
    ref = 640.93
    half = round(ref / 2, 2)
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "investable_eur": ref,
                "allocations": [
                    {"symbol": "STX", "target_eur": half, "model_weight_pct": 50.0, "side": "BUY"},
                    {"symbol": "SPY", "target_eur": round(ref - half, 2), "model_weight_pct": 50.0, "side": "BUY"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_freigabe_latest.json").write_text(
        json.dumps({"updated_at_utc": "2026-06-08T00:53:00+00:00", "prep_steps": []}),
        encoding="utf-8",
    )
    html = render_r3_exec_mirror_page(tmp_path).decode("utf-8")
    assert "r3-mirror-results" in html
    assert "r3-panels-stack" in html
    assert "r3-freigabe-btn" in html
    assert "r3-pipeline-facts" not in html
    assert "r3-cycle-facts" not in html
    assert "r3-system-facts" not in html
    assert "Kanäle" not in html
    assert "runtime_profile" not in html
    assert "r3-viewport-fit" in html
    assert "r3EnsureNativeViewport" in html
    assert "r3-mirror-model" in html
    assert "r3-trading-functions" in html
    assert "r3PollMirror" in html
    assert "Plan" in html
    assert "r3FreigabeSubmit" in html
    assert "r3PatchMirrorDisplays" in html
    assert "STX" in html
    assert "SPY" in html
    assert 'class="r3-mirror-title">R3</h1>' in html
    assert 'data-exec-mode="1"' in html
    assert 'class="r3-mirror-empty"' not in html
    assert "r3-freigabe-governance" not in html
    assert 'id="r3-mirror-live"' not in html
    assert "/assets/r3-icon.svg" in html
    assert "r3-freigabe-btn" in html
    assert "T212" in html
    assert 'class="r3-stock-btn' not in html
    assert 'id="r3-einzel-wrap"' not in html
    assert "Ausführung" not in html
    assert "r3-mirror-portfolio" not in html
    assert 'r3-mirror-k">Zeilen</span>' not in html
