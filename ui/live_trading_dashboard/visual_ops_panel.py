"""Graphisches Ops-Panel — Active Alpha Live-Cockpit (Dashboard-Oberfläche)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from ui.invest_layout import body_label, set_banner
from ui.interactive_cockpit.cockpit_theme import BORDER, SUCCESS_BANNER, TEXT_PRIMARY, WARNING_BANNER

STAGE_ORDER = ("sportwagen", "sport_plus", "track_day", "rennsport", "rennwagen")
STAGE_LABELS = {
    "sportwagen": "Sportwagen",
    "sport_plus": "Sport+",
    "track_day": "Track",
    "rennsport": "Rennsport",
    "rennwagen": "Rennwagen",
}


def _pill_style(active: bool, done: bool) -> str:
    if active:
        return (
            f"background:{WARNING_BANNER}; color:{TEXT_PRIMARY}; font-weight:700;"
            f"padding:6px 10px; border-radius:14px; border:2px solid #c9a227;"
        )
    if done:
        return (
            f"background:{SUCCESS_BANNER}; color:{TEXT_PRIMARY};"
            f"padding:6px 10px; border-radius:14px; border:1px solid {BORDER};"
        )
    return (
        f"background:transparent; color:#888; padding:6px 10px;"
        f"border-radius:14px; border:1px dashed {BORDER};"
    )


class VisualOpsPanel(QWidget):
    """Live-Status: Ampel, Evolution-Stufenleiter, Fortschrittsbalken."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._headline = body_label("Systemstatus wird geladen …")
        set_banner(self._headline, "info")
        lay.addWidget(self._headline)

        ampel_row = QHBoxLayout()
        self._ampel = QLabel("● ● ●")
        self._ampel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ampel.setStyleSheet("font-size:18pt; letter-spacing:8px; padding:8px;")
        ampel_row.addWidget(self._ampel)
        self._traffic_text = QLabel("Ampel: —")
        self._traffic_text.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ampel_row.addWidget(self._traffic_text, stretch=1)
        lay.addLayout(ampel_row)

        ladder_row = QHBoxLayout()
        ladder_row.setSpacing(4)
        self._stage_pills: List[QLabel] = []
        for sid in STAGE_ORDER:
            pill = QLabel(STAGE_LABELS[sid])
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setStyleSheet(_pill_style(False, False))
            ladder_row.addWidget(pill)
            self._stage_pills.append(pill)
        lay.addLayout(ladder_row)

        self._progress_label = QLabel("Fortschritt nächste Stufe")
        lay.addWidget(self._progress_label)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        lay.addWidget(self._progress)

        chips_row = QHBoxLayout()
        self._chip_t212 = body_label("T212 —")
        self._chip_quotes = body_label("Kurse —")
        self._chip_learn = body_label("Lernen —")
        self._chip_auto = body_label("Auto —")
        for c in (self._chip_t212, self._chip_quotes, self._chip_learn, self._chip_auto):
            c.setMinimumWidth(120)
            chips_row.addWidget(c)
        lay.addLayout(chips_row)

        self._pulse = body_label("Bereit")
        set_banner(self._pulse, "info")
        lay.addWidget(self._pulse)

    def set_pulse(self, text: str, *, kind: str = "info") -> None:
        self._pulse.setText(text)
        set_banner(self._pulse, kind)

    def _set_ampel(self, traffic: str) -> None:
        t = str(traffic or "GELB").upper()
        colors = {
            "GRUEN": ("#2ecc71", "#555", "#555"),
            "GELB": ("#f1c40f", "#f1c40f", "#555"),
            "ROT": ("#e74c3c", "#555", "#555"),
        }
        c = colors.get(t, colors["GELB"])
        self._ampel.setText(
            f'<span style="color:{c[0]}">●</span> '
            f'<span style="color:{c[1]}">●</span> '
            f'<span style="color:{c[2]}">●</span>'
        )
        self._ampel.setTextFormat(Qt.TextFormat.RichText)
        labels = {"GRUEN": "Grün — OK", "GELB": "Gelb — Achtung", "ROT": "Rot — Blocker"}
        self._traffic_text.setText(f"Ampel: {labels.get(t, t)}")

    def _set_ladder(self, current_id: str) -> None:
        try:
            idx = STAGE_ORDER.index(current_id)
        except ValueError:
            idx = 0
        for i, pill in enumerate(self._stage_pills):
            pill.setStyleSheet(_pill_style(i == idx, i < idx))

    def _set_progress_from_gaps(self, progress: Dict[str, Any], live_mature: int) -> None:
        next_id = progress.get("next_stage_id") or "sport_plus"
        gaps = progress.get("gaps_de") or []
        target = 3
        if next_id == "sport_plus":
            target = 3
            val = min(100, int(100 * live_mature / max(1, target)))
            self._progress.setValue(val)
            self._progress.setFormat(f"Live-Fills {live_mature}/{target} → Sport Plus")
        elif next_id == "track_day":
            target = 10
            val = min(100, int(100 * live_mature / target))
            self._progress.setValue(val)
            self._progress.setFormat(f"Live-Fills {live_mature}/{target} → Track Day")
        else:
            self._progress.setValue(100 if progress.get("ready_for_next") else 0)
            self._progress.setFormat(
                "Bereit für nächste Stufe" if progress.get("ready_for_next") else "Kriterien offen"
            )
        self._progress_label.setText(
            f"Ziel: {progress.get('next_label_de') or next_id}"
            + (f" — {' · '.join(gaps[:2])}" if gaps else "")
        )

    def update_from_snap(self, root: Path, snap: Dict[str, Any]) -> None:
        root = Path(root)
        traffic = str(snap.get("traffic") or "GELB")
        self._set_ampel(traffic)

        pl = snap.get("public_learning") or {}
        stage_id = str(pl.get("stage_id") or "sportwagen")
        self._set_ladder(stage_id)

        live_m = int(pl.get("live_mature") or 0)
        prog = pl.get("stage_progress")
        if not isinstance(prog, dict) or not prog:
            try:
                from analytics.evolution_stage_runner import stage_criteria_progress

                prog = stage_criteria_progress(root, snap)
            except Exception:
                prog = {"next_stage_id": "sport_plus", "gaps_de": []}
        self._set_progress_from_gaps(prog, live_m)

        broker = snap.get("broker") or {}
        cash = broker.get("cash_eur")
        if broker.get("error") and cash is None:
            set_banner(self._chip_t212, "err")
            self._chip_t212.setText("T212 ✗")
        elif cash is not None:
            set_banner(self._chip_t212, "ok")
            self._chip_t212.setText(f"T212 ✓ {float(cash):,.0f}€")
        else:
            set_banner(self._chip_t212, "warn")
            self._chip_t212.setText("T212 ?")

        qc = snap.get("quote_coverage") or {}
        if qc.get("ok"):
            set_banner(self._chip_quotes, "ok")
            self._chip_quotes.setText(f"Kurse ✓ {qc.get('quote_coverage_label_de', '')[:12]}")
        else:
            set_banner(self._chip_quotes, "err" if qc else "warn")
            self._chip_quotes.setText(f"Kurse ✗ {qc.get('quote_coverage_label_de', '—')[:12]}")

        score = pl.get("score")
        if score is not None:
            kind = "ok" if int(score) >= 70 else "warn"
            set_banner(self._chip_learn, kind)
            self._chip_learn.setText(f"Lernen {score}/100")
        else:
            set_banner(self._chip_learn, "warn")
            self._chip_learn.setText("Lernen —")

        applied = int(pl.get("auto_applied_count") or 0)
        set_banner(self._chip_auto, "ok" if applied else "info")
        self._chip_auto.setText(f"Auto-Tuning {applied}")

        status = snap.get("rebalance_status") or {}
        summary = status.get("summary_de") or snap.get("today_action_de") or "—"
        banner = {"GRUEN": "ok", "GELB": "warn", "ROT": "err"}.get(traffic, "warn")
        self._headline.setText(f"{pl.get('stage_de', 'Sportwagen')} · {summary}"[:200])
        set_banner(self._headline, banner)
