"""R3 Zentrale — Registry und Policy."""
from pathlib import Path

from analytics.r3_central_registry import (
    build_32b_r3_central_mandate,
    build_r3_central_status,
    load_central_policy,
    render_r3_central_section,
)


def test_central_policy_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_central_policy(root)
    assert policy.get("status") == "AUTHORITATIVE"
    assert "17890" in str(policy.get("hub_base_de") or "")


def test_build_r3_central_status(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_central_source_policy.json").write_text(
        '{"headline_de":"R3","hub_base_de":"http://127.0.0.1:17890"}',
        encoding="utf-8",
    )
    doc = build_r3_central_status(tmp_path, persist=True)
    assert doc.get("feeds_total", 0) >= 4
    assert (tmp_path / "evidence/r3_central_latest.json").is_file()


def test_render_section_contains_hub() -> None:
    root = Path(__file__).resolve().parents[1]
    html_out = render_r3_central_section(root)
    assert "R3 Zentrale" in html_out
    assert "17890" in html_out


def test_mandate_written(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_central_source_policy.json").write_text("{}", encoding="utf-8")
    text = build_32b_r3_central_mandate(tmp_path)
    assert "König-Mandat" in text
    assert (tmp_path / "evidence/king_32b_r3_central_mandate.txt").is_file()
