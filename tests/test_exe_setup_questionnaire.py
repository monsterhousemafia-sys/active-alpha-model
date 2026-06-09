from __future__ import annotations

from pathlib import Path

from aa_exe_setup_questionnaire import load_exe_setup_permissions, selected_response, setup_pending


def test_load_exe_setup_permissions_questionnaire():
    root = Path(__file__).resolve().parents[1]
    doc = load_exe_setup_permissions(root)
    assert doc is not None
    assert doc.get("questionnaire_id") == "EXE_OPERATIONAL_SETUP_PERMISSIONS"
    assert len(doc.get("responses") or []) == 4
    auto = selected_response(root, "auto_trading")
    assert auto is not None
    assert auto.get("selected_option_id") == "auto_limited"
    assert setup_pending(root) is True
