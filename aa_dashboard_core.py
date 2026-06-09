from __future__ import annotations

import os
from collections import deque
from time import monotonic
from typing import Any, Deque, Dict, Optional, Tuple

from aa_version import APP_TITLE

BACKTEST_PIPELINE: Tuple[Tuple[str, str], ...] = (
    ("universe", "Tickeruniversum"),
    ("features", "Marktdaten & Features"),
    ("ml", "Walk-forward ML"),
    ("path", "Pfad-Simulation"),
    ("export", "Reports & Export"),
)

BACKTEST_PIPELINE_WEIGHTS: Dict[str, float] = {
    "universe": 0.04,
    "features": 0.22,
    "ml": 0.48,
    "path": 0.21,
    "export": 0.05,
}

LAUNCHER_STEP_WEIGHTS: Dict[str, float] = {
    "env": 0.06,
    "libs": 0.10,
    "core": 0.03,
    "ops": 0.06,
    "paper": 0.07,
    "run": 0.68,
}

_PIPELINE_LABELS: Dict[str, str] = {k: v for k, v in BACKTEST_PIPELINE}

_PHASE_TO_PIPELINE: Dict[str, str] = {
    "Tickeruniversum laden": "universe",
    "Marktdaten laden": "features",
    "Feature Engineering": "features",
    "Cross-Sectional Ranking": "features",
    "Universum filtern": "features",
    "Feature-Datei schreiben": "features",
    "Walk-forward ML (Phase A)": "ml",
    "Parallel Prediction Pipeline": "ml",
    "Pfad-Simulation (Phase B)": "path",
    "Walk-forward Execution Simulation": "path",
    "Walk-forward Backtest": "path",
    "Naive Momentum Baselines": "path",
    "Backtest-Dateien schreiben": "export",
    "Aktuelles Signal": "export",
    "Signal-Dateien schreiben": "export",
}


def _estimate_eta(elapsed: float, ratio: float, tracker: Optional["_EtaTracker"]) -> Optional[float]:
    if ratio < 0.005:
        return None
    if ratio >= 0.995:
        return 0.0
    linear = elapsed * (1.0 - ratio) / max(ratio, 1e-6)
    if tracker is None:
        return linear
    return tracker.estimate(elapsed, ratio, linear)


class _EtaTracker:
    """Blend linear ETA with smoothed progress velocity."""

    def __init__(self) -> None:
        self._last_ratio = 0.0
        self._last_elapsed = 0.0
        self._speed: Optional[float] = None

    def estimate(self, elapsed: float, ratio: float, linear: float) -> float:
        if self._last_elapsed > 0 and ratio > self._last_ratio:
            dt = elapsed - self._last_elapsed
            dr = ratio - self._last_ratio
            if dt >= 0.8 and dr > 0:
                inst = dr / dt
                self._speed = inst if self._speed is None else (0.65 * self._speed + 0.35 * inst)
        self._last_ratio = ratio
        self._last_elapsed = elapsed
        if self._speed and self._speed > 1e-6:
            rate_eta = (1.0 - ratio) / self._speed
            return max(0.0, 0.6 * rate_eta + 0.4 * linear)
        return linear


class DashboardCore:
    """Shared progress state for console and Qt dashboards."""

    def __init__(self, *, title: Optional[str] = None) -> None:
        self.title = title or self.default_title()
        self.out_dir = ""
        self.started_at = monotonic()
        self.status: Dict[str, Any] = {}
        self.logs: Deque[str] = deque(maxlen=200)
        self._pipeline_status: Dict[str, str] = {key: "pending" for key, _ in BACKTEST_PIPELINE}
        self._pipeline_active: Optional[str] = None
        self._internal_phase = ""
        self._sub_step = ""
        self._sub_total = 1
        self._sub_completed = 0
        self.finished = False
        self.last_error = ""
        self._eta_tracker = _EtaTracker()

    @staticmethod
    def default_title() -> str:
        return APP_TITLE

    def reset_timer(self) -> None:
        self.started_at = monotonic()

    def _pipeline_index(self, key: str) -> int:
        for i, (k, _label) in enumerate(BACKTEST_PIPELINE):
            if k == key:
                return i
        return -1

    def _pipeline_label(self, key: Optional[str]) -> str:
        if key is None:
            return "Initialisierung"
        return _PIPELINE_LABELS.get(key, key)

    def _activate_pipeline_step(self, key: str) -> None:
        idx = self._pipeline_index(key)
        if idx < 0:
            return
        if self._pipeline_active and self._pipeline_active != key:
            self._pipeline_status[self._pipeline_active] = "done"
        for i, (k, _label) in enumerate(BACKTEST_PIPELINE):
            if i < idx and self._pipeline_status.get(k) not in {"done", "skipped"}:
                self._pipeline_status[k] = "done"
        self._pipeline_status[key] = "active"
        self._pipeline_active = key

    def complete_pipeline_step(self, key: str) -> None:
        idx = self._pipeline_index(key)
        if idx < 0:
            return
        for i, (k, _label) in enumerate(BACKTEST_PIPELINE):
            if i <= idx:
                self._pipeline_status[k] = "done"
        self._pipeline_active = None

    def progress_ratio(self) -> float:
        done = 0.0
        for key, weight in BACKTEST_PIPELINE_WEIGHTS.items():
            status = self._pipeline_status.get(key, "pending")
            if status in {"done", "skipped"}:
                done += weight
            elif status == "active" and key == self._pipeline_active and self._sub_total > 0:
                frac = min(max(self._sub_completed / self._sub_total, 0.0), 1.0)
                done += weight * frac
        return min(done, 1.0)

    def progress_pct(self) -> int:
        return int(round(self.progress_ratio() * 100.0))

    def eta_seconds(self, elapsed: float) -> Optional[float]:
        ratio = self.progress_ratio()
        try:
            from aa_eta_calibration import estimate_backtest_remaining

            if self.out_dir:
                calibrated = estimate_backtest_remaining(
                    pipeline_status=self._pipeline_status,
                    active_key=self._pipeline_active,
                    sub_completed=self._sub_completed,
                    sub_total=self._sub_total,
                    elapsed=elapsed,
                    out_dir=self.out_dir,
                )
                if calibrated is not None:
                    blended = _estimate_eta(elapsed, ratio, self._eta_tracker)
                    if blended is not None:
                        return max(0.0, 0.6 * calibrated + 0.4 * blended)
                    return max(0.0, calibrated)
        except Exception:
            pass
        return _estimate_eta(elapsed, ratio, self._eta_tracker)

    def activity_line(self) -> str:
        parts: list[str] = []
        if self._sub_step:
            parts.append(self._sub_step)
        elif self._pipeline_active:
            parts.append(self._pipeline_label(self._pipeline_active))
        else:
            parts.append("Bereit")
        for key, label in [
            ("rebalance", "Rebalance"),
            ("date", "Datum"),
            ("train_rows", "Train"),
            ("candidates", "Kandidaten"),
            ("ticker", "Ticker"),
        ]:
            val = self.status.get(key)
            if val not in (None, ""):
                parts.append(f"{label} {val}")
        return " | ".join(parts)[:160]

    def start_phase(self, name: str, *, total: int = 1, step: str = "") -> None:
        self._internal_phase = name
        self._sub_step = step or name
        self._sub_completed = 0
        self._sub_total = max(int(total), 1)
        key = _PHASE_TO_PIPELINE.get(name)
        if key and key != self._pipeline_active:
            self._activate_pipeline_step(key)
        self.status = {}

    def set_status(self, **kwargs: Any) -> None:
        self.status.update({k: v for k, v in kwargs.items() if v is not None})
        if kwargs.get("step"):
            self._sub_step = str(kwargs["step"])

    def advance_phase(self, advance: int = 1, **kwargs: Any) -> None:
        if kwargs:
            self.set_status(**kwargs)
        self._sub_completed = min(self._sub_completed + int(advance), self._sub_total)

    def finish_phase(self) -> None:
        self._sub_completed = self._sub_total

    def log(self, level: str, message: str) -> None:
        self.logs.append(f"[{level}] {message}")

    def ok(self, message: str) -> None:
        low = message.lower()
        if "feature-cache geladen" in low or ("feature-cache" in low and "geladen" in low):
            self.complete_pipeline_step("features")
        elif "prediction-cache geladen" in low:
            self.complete_pipeline_step("ml")
        self.log("OK", message)

    def warn(self, message: str) -> None:
        self.log("WARN", message)

    def error(self, message: str) -> None:
        self.last_error = message
        self.log("ERROR", message)

    def mark_complete(self) -> None:
        for key, _label in BACKTEST_PIPELINE:
            if self._pipeline_status.get(key) == "pending":
                self._pipeline_status[key] = "done"
        self._pipeline_active = None
        self.finished = True

    @property
    def phase_index(self) -> int:
        if self._pipeline_active is None:
            return sum(1 for s in self._pipeline_status.values() if s in {"done", "skipped"})
        return self._pipeline_index(self._pipeline_active) + 1

    @property
    def total_phases(self) -> int:
        return len(BACKTEST_PIPELINE)

    @total_phases.setter
    def total_phases(self, value: int) -> None:
        _ = value

    @property
    def phase_name(self) -> str:
        return self._pipeline_label(self._pipeline_active)

    @phase_name.setter
    def phase_name(self, value: str) -> None:
        self._internal_phase = value

    @property
    def phase_step(self) -> str:
        return self._sub_step

    @phase_step.setter
    def phase_step(self, value: str) -> None:
        self._sub_step = value

    @property
    def phase_total(self) -> int:
        return self._sub_total

    @phase_total.setter
    def phase_total(self, value: int) -> None:
        self._sub_total = max(int(value), 1)

    @property
    def phase_completed(self) -> int:
        return self._sub_completed

    @phase_completed.setter
    def phase_completed(self, value: int) -> None:
        self._sub_completed = int(value)


LAUNCHER_STEPS: Tuple[Tuple[str, str], ...] = (
    ("env", "Python-Umgebung (.venv)"),
    ("libs", "Bibliotheken laden"),
    ("core", "Core-Check"),
    ("ops", "Betriebsdaten aktualisieren"),
    ("paper", "Paper Mark-to-Market"),
    ("run", f"{APP_TITLE} Analyse"),
)


class LauncherDashboardCore:
    """Progress state for Marktanalyse.exe bootstrap."""

    def __init__(self) -> None:
        self.title = APP_TITLE
        self.started_at = monotonic()
        self.logs: Deque[str] = deque(maxlen=200)
        self._status = {key: "pending" for key, _ in LAUNCHER_STEPS}
        self._active: Optional[str] = None
        self._activity = "Initialisierung …"
        self.last_error = ""
        self.finished = False
        self._run_ratio = 0.0
        self._eta_tracker = _EtaTracker()

    def reset_timer(self) -> None:
        self.started_at = monotonic()
        self._eta_tracker = _EtaTracker()

    def set_run_progress(self, ratio: float) -> None:
        """Backtest handoff: 0..1 progress within the 'run' launcher step."""
        self._run_ratio = min(max(float(ratio), 0.0), 1.0)

    def _progress_ratio(self) -> float:
        done = 0.0
        for key, weight in LAUNCHER_STEP_WEIGHTS.items():
            status = self._status.get(key, "pending")
            if status == "done":
                done += weight
            elif status == "active" and key == self._active:
                partial = 0.35
                if key == "run":
                    partial = max(self._run_ratio, 0.08)
                done += weight * partial
        return min(done, 1.0)

    def progress_pct(self) -> int:
        return int(round(self._progress_ratio() * 100.0))

    def eta_seconds(self, elapsed: float) -> Optional[float]:
        try:
            from aa_eta_calibration import estimate_launcher_remaining

            calibrated = estimate_launcher_remaining(
                status=self._status,
                active_key=self._active,
                run_sub_ratio=self._run_ratio,
                elapsed=elapsed,
            )
            if calibrated is not None:
                linear = _estimate_eta(elapsed, self._progress_ratio(), self._eta_tracker)
                if linear is not None:
                    return max(0.0, 0.6 * calibrated + 0.4 * linear)
                return max(0.0, calibrated)
        except Exception:
            pass
        return _estimate_eta(elapsed, self._progress_ratio(), self._eta_tracker)

    def activity_line(self) -> str:
        return self._activity

    def activate(self, key: str) -> None:
        idx = next(i for i, (k, _) in enumerate(LAUNCHER_STEPS) if k == key)
        for i, (k, _) in enumerate(LAUNCHER_STEPS):
            if i < idx and self._status.get(k) != "done":
                self._status[k] = "done"
        self._status[key] = "active"
        self._active = key
        self._activity = next(lbl for k, lbl in LAUNCHER_STEPS if k == key)

    def done(self, key: str) -> None:
        self._status[key] = "done"
        if self._active == key:
            self._active = None

    def log(self, message: str) -> None:
        self.logs.append(message)

    def mark_complete(self) -> None:
        for key, _ in LAUNCHER_STEPS:
            if self._status.get(key) != "done":
                self._status[key] = "done"
        self._active = None
        self.finished = True
