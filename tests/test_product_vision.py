from pathlib import Path

from aa_product_vision import load_product_vision, roadmap_phases


def test_product_vision_loaded():
    root = Path(__file__).resolve().parents[1]
    doc = load_product_vision(root)
    assert doc is not None
    assert doc.get("vision_id") == "PROFESSIONAL_EXE_MULTI_USER_WITH_HUMAN_COMPARISON"
    phases = roadmap_phases(root)
    assert len(phases) >= 4
    assert doc.get("status") == "SAVED_FOR_FUTURE_DEVELOPMENT"
