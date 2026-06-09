from __future__ import annotations

import os
from pathlib import Path
from time import monotonic
from typing import Any, Dict, Optional, Tuple

from aa_bios_ui import (
    BIOS_VERSION,
    STYLE_ACCENT,
    STYLE_BOLD,
    STYLE_DIM,
    STYLE_FG,
    LiveRenderable,
    bios_banner,
    bios_hint,
    bios_panel,
    bios_text,
    create_console,
    fmt_seconds,
    progress_line,
    step_label_style,
    step_marker,
)
from aa_dashboard_core import BACKTEST_PIPELINE, DashboardCore
from aa_ui_pump import plain_progress_quiet

# Re-export for compatibility
__all__ = ["RunDashboard", "BACKTEST_PIPELINE"]


class RunDashboard:
    """Console dashboard (Rich BIOS) — fallback when Qt is unavailable."""

    def __init__(self, *, enabled: bool = True, title: Optional[str] = None, use_rich: bool = True) -> None:
        self.enabled = enabled
        self.rich = False
        self.console = None
        self.live = None
        self._core = DashboardCore(title=title or DashboardCore.default_title())
        self.title = self._core.title
        self._last_refresh = 0.0
        self._live_view: Any = None
        self._use_rich = use_rich
        if enabled and use_rich:
            try:
                from rich import box
                from rich.console import Console, Group
                from rich.live import Live
                from rich.panel import Panel
                from rich.table import Table
                from rich.text import Text

                self._rich_classes = {
                    "Console": Console,
                    "Group": Group,
                    "Live": Live,
                    "Panel": Panel,
                    "Table": Table,
                    "Text": Text,
                    "box": box,
                }
                self.console = create_console(Console)
                self.rich = True
            except Exception:
                self.rich = False

    @staticmethod
    def _default_title() -> str:
        return DashboardCore.default_title()

    @staticmethod
    def _fmt_seconds(seconds: float) -> str:
        return fmt_seconds(seconds)

    def _progress_ratio(self) -> float:
        return self._core.progress_ratio()

    def _progress_pct(self) -> int:
        return self._core.progress_pct()

    def _eta_seconds(self, elapsed: float) -> Optional[float]:
        return self._core.eta_seconds(elapsed)

    def _activity_line(self) -> str:
        return self._core.activity_line()

    def _bar_text(self) -> str:
        return progress_line(
            self._core.progress_ratio(),
            sub_completed=self._core._sub_completed,
            sub_total=self._core._sub_total,
        )

    def _step_symbol(self, state: str) -> Tuple[str, str]:
        return step_marker(state)

    def _panel(self, content: Any, title: str) -> Any:
        C = self._rich_classes
        return bios_panel(content, title, Panel=C["Panel"], box=C.get("box"))

    def _render_body(self) -> Any:
        C = self._rich_classes
        steps = list(enumerate(BACKTEST_PIPELINE, start=1))
        mid = (len(steps) + 1) // 2
        left_steps, right_steps = steps[:mid], steps[mid:]

        grid = C["Table"](show_header=False, box=None, padding=(0, 1), expand=True)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)

        def step_table(items: list) -> Any:
            tbl = C["Table"](show_header=False, box=None, padding=(0, 0), expand=True)
            tbl.add_column("", width=4, justify="center")
            tbl.add_column("", style=STYLE_FG)
            for i, (key, label) in items:
                state = self._core._pipeline_status.get(key, "pending")
                sym, sym_style = self._step_symbol(state)
                lbl_style = step_label_style(state)
                tbl.add_row(
                    bios_text(C["Text"], sym, style=sym_style),
                    bios_text(C["Text"], f"{i}. {label}", style=lbl_style),
                )
            return tbl

        grid.add_row(step_table(left_steps), step_table(right_steps))

        elapsed = monotonic() - self._core.started_at
        eta = self._eta_seconds(elapsed)
        eta_txt = f"~{self._fmt_seconds(eta)}" if eta is not None else "---"

        footer = C["Table"](show_header=False, box=None, padding=(1, 0), expand=True)
        footer.add_column(ratio=1)
        footer.add_row(bios_text(C["Text"], f"STATUS: {self._activity_line()}", style=STYLE_FG))
        footer.add_row(
            bios_text(C["Text"], self._bar_text(), style=STYLE_ACCENT, justify="center")
        )
        time_row = C["Table"](show_header=False, box=None, padding=(0, 0), expand=True)
        time_row.add_column(ratio=1)
        time_row.add_column(ratio=1, justify="right")
        time_row.add_row(
            bios_text(C["Text"], f"ELAPSED {self._fmt_seconds(elapsed)}", style=STYLE_BOLD),
            bios_text(C["Text"], f"ETA {eta_txt}", style=STYLE_DIM),
        )
        footer.add_row(time_row)
        footer.add_row(bios_hint(C["Text"]))

        body = C["Table"](show_header=False, box=None, padding=0, expand=True)
        body.add_column(ratio=1)
        body.add_row(bios_banner(C["Text"], self.title))
        body.add_row(grid)
        body.add_row(footer)
        return body

    def _render(self) -> Any:
        C = self._rich_classes
        log_text = "\n".join(self._core.logs) if self._core.logs else "No messages."
        return C["Group"](
            self._panel(self._render_body(), "Setup Utility"),
            self._panel(bios_text(C["Text"], log_text), "System Log"),
        )

    def refresh(self, *, force: bool = False) -> None:
        if not (self.rich and self.live is not None):
            return
        now = monotonic()
        if not force and (now - self._last_refresh) < 0.35:
            return
        self._last_refresh = now
        try:
            self.live.refresh()
        except Exception:
            pass

    def start(self, *, total_phases: int, out_dir: Path, title: Optional[str] = None) -> None:
        _ = total_phases
        if title:
            self.title = title
            self._core.title = title
        self._core.out_dir = str(out_dir)
        self._core.reset_timer()
        if self.rich:
            try:
                C = self._rich_classes
                self._live_view = LiveRenderable(self._render)
                self.live = C["Live"](
                    self._live_view,
                    console=self.console,
                    refresh_per_second=2,
                    auto_refresh=True,
                    transient=False,
                    screen=True,
                )
                self.live.start()
            except Exception:
                self.rich = False
                self.live = None
                self._print_plain()
        else:
            self._print_plain()

    def _print_plain(self) -> None:
        width = 62
        print("\n+" + "-" * width + "+")
        print(f"| {BIOS_VERSION:<{width - 2}} |")
        print(f"| Copyright (C) Active Alpha Model{' ' * (width - 33)} |")
        print("+" + "-" * width + "+")
        print(f"| {self.title.upper():<{width - 2}} |")
        print("+" + "-" * width + "+")
        for i, (key, label) in enumerate(BACKTEST_PIPELINE, start=1):
            sym = {"done": "[X]", "active": "[*]", "skipped": "[--]"}.get(
                self._core._pipeline_status.get(key, "pending"), "[ ]"
            )
            print(f"| {sym} {i}. {label:<{width - 8}} |")
        print("+" + "-" * width + "+")
        print(f"| STATUS: {self._activity_line():<{width - 10}} |")
        print(f"| {self._bar_text():<{width - 2}} |")
        elapsed = monotonic() - self._core.started_at
        eta = self._eta_seconds(elapsed)
        eta_txt = f"~{self._fmt_seconds(eta)}" if eta is not None else "---"
        print(f"| ELAPSED {self._fmt_seconds(elapsed):>8}    ETA {eta_txt:>12}{' ' * (width - 40)} |")
        print("+" + "-" * width + "+")

    def start_phase(self, name: str, *, total: int = 1, step: str = "") -> None:
        self._core.start_phase(name, total=total, step=step)
        if plain_progress_quiet():
            return
        self.refresh()
        if not self.rich:
            self._print_plain()

    def set_status(self, **kwargs: Any) -> None:
        self._core.set_status(**kwargs)
        if plain_progress_quiet():
            return
        self.refresh()

    def advance_phase(self, advance: int = 1, **kwargs: Any) -> None:
        self._core.advance_phase(advance, **kwargs)
        if plain_progress_quiet():
            return
        self.refresh()

    def finish_phase(self) -> None:
        self._core.finish_phase()
        if plain_progress_quiet():
            return
        self.refresh()

    def complete_pipeline_step(self, key: str) -> None:
        self._core.complete_pipeline_step(key)
        if plain_progress_quiet():
            return
        self.refresh()

    def ok(self, message: str) -> None:
        self._core.ok(message)
        if plain_progress_quiet():
            return
        self.refresh()

    def warn(self, message: str) -> None:
        self._core.warn(message)
        if plain_progress_quiet():
            return
        self.refresh()

    def error(self, message: str) -> None:
        self._core.error(message)
        if plain_progress_quiet():
            return
        self.refresh()

    def stop(self) -> None:
        try:
            self._core.mark_complete()
            if self.rich and self.live is not None:
                self.refresh(force=True)
                self.live.stop()
                self.live = None
        except Exception:
            pass

    @property
    def phase_index(self) -> int:
        return self._core.phase_index

    @property
    def total_phases(self) -> int:
        return self._core.total_phases

    @total_phases.setter
    def total_phases(self, value: int) -> None:
        self._core.total_phases = value

    @property
    def phase_name(self) -> str:
        return self._core.phase_name

    @phase_name.setter
    def phase_name(self, value: str) -> None:
        self._core.phase_name = value

    @property
    def phase_step(self) -> str:
        return self._core.phase_step

    @phase_step.setter
    def phase_step(self, value: str) -> None:
        self._core.phase_step = value

    @property
    def phase_total(self) -> int:
        return self._core.phase_total

    @phase_total.setter
    def phase_total(self, value: int) -> None:
        self._core.phase_total = value

    @property
    def phase_completed(self) -> int:
        return self._core.phase_completed

    @phase_completed.setter
    def phase_completed(self, value: int) -> None:
        self._core.phase_completed = value
