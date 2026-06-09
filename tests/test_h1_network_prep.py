from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_run_h1_network_prep() -> None:
    from analytics.h1_network_prep import run_h1_network_prep

    doc = run_h1_network_prep(ROOT, phase="execute")
    assert doc.get("ok") is True
    assert "steps" in doc
    assert len(doc.get("steps") or []) >= 2
    assert (ROOT / "evidence/h1_network_prep_latest.json").is_file()


def test_king_h1_prep_script_exists() -> None:
    path = ROOT / "tools/king_h1_prep.sh"
    assert path.is_file()
    import os
    import stat

    assert path.stat().st_mode & stat.S_IXUSR
