from __future__ import annotations

import json
from pathlib import Path

from analytics.whatsapp_terminal_finish import finish_terminal_task


def test_finish_terminal_task(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/whatsapp_spread.json").write_text(
        json.dumps({"auto_send_mode": "auto", "self_phone_e164": "4915756402383"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/whatsapp_spread_latest.json").write_text(
        json.dumps(
            {
                "send_ok": False,
                "prepare_ok": True,
                "delivery_mode": "manual_prepare",
                "phone_e164": "4915756402383",
                "steps": [{"kind": "join_check", "join_url": "https://x/join"}],
            }
        ),
        encoding="utf-8",
    )
    doc = finish_terminal_task(tmp_path)
    assert doc.get("status") == "beendet"
    cfg = json.loads((tmp_path / "control/whatsapp_spread.json").read_text(encoding="utf-8"))
    assert cfg.get("auto_send_mode") == "manual"
    assert cfg.get("terminal_task", {}).get("status") == "beendet"
