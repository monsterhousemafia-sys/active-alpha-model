"""Bootstrap V1 vision automation artifacts (non-operative)."""
from __future__ import annotations

from pathlib import Path

from aa_evidence_status import export_evidence_status
from aa_vision_controller import bootstrap_vision_automation

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    bootstrap_vision_automation(root)
    export_evidence_status(root)
    print("V1 bootstrap complete")
