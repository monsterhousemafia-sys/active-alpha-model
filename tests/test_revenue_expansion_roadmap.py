from pathlib import Path

from aa_revenue_expansion_roadmap import current_phase, load_revenue_expansion_roadmap, next_immediate_actions


def test_revenue_expansion_roadmap():
    root = Path(__file__).resolve().parents[1]
    doc = load_revenue_expansion_roadmap(root)
    assert doc is not None
    assert doc.get("roadmap_id") == "REVENUE_FUNDED_PRODUCT_AND_AGENT_EXPANSION"
    phase = current_phase(root)
    assert phase is not None
    assert phase.get("phase_id") == "R2"
    actions = next_immediate_actions(root)
    assert len(actions) >= 1
