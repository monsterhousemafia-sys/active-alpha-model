"""Shared BIOS-style console theme for Marktanalyse UI."""
from __future__ import annotations

from typing import Any, Callable, Tuple

STYLE_FG = "white on blue"
STYLE_BOLD = "bold white on blue"
STYLE_DIM = "dim white on blue"
STYLE_TITLE = "bold yellow on blue"
STYLE_ACCENT = "bold cyan on blue"
STYLE_ACTIVE = "black on cyan"
STYLE_BORDER = "white on blue"
BAR_WIDTH = 44
BAR_FILL = "#"
BAR_EMPTY = "-"
BIOS_VENDOR = "Active Alpha Model"
BIOS_VERSION = "Marktanalyse BIOS v2.0"


class LiveRenderable:
    """Re-render callback on each Live paint (clock + progress without update flicker)."""

    def __init__(self, render_fn: Callable[[], Any]) -> None:
        self._render_fn = render_fn

    def __rich_console__(self, console: Any, options: Any) -> Any:
        renderable = self._render_fn()
        yield from console.render(renderable, options)


def bios_text(Text: Any, content: str, *, style: str = STYLE_FG, justify: str | None = None) -> Any:
    text = Text()
    text.append(content, style=style)
    if justify is not None:
        text.justify = justify
    return text


def fmt_seconds(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    h, rem = divmod(seconds, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def progress_bar(ratio: float) -> str:
    filled = int(round(BAR_WIDTH * max(0.0, min(ratio, 1.0))))
    return BAR_FILL * filled + BAR_EMPTY * (BAR_WIDTH - filled)


def progress_line(ratio: float, *, sub_completed: int = 0, sub_total: int = 0) -> str:
    pct = int(round(max(0.0, min(ratio, 1.0)) * 100.0))
    bar = progress_bar(ratio)
    if sub_total > 1:
        return f"PROGRESS {sub_completed:>{len(str(sub_total))}}/{sub_total} [{bar}] {pct:3d}%"
    return f"PROGRESS [{bar}] {pct:3d}%"


def step_marker(state: str) -> Tuple[str, str]:
    if state == "done":
        return "[X]", STYLE_BOLD
    if state == "active":
        return "[*]", STYLE_ACTIVE
    if state == "skipped":
        return "[--]", STYLE_DIM
    return "[ ]", STYLE_DIM


def step_label_style(state: str) -> str:
    if state == "active":
        return STYLE_ACTIVE
    if state == "done":
        return STYLE_BOLD
    if state == "skipped":
        return STYLE_DIM
    return STYLE_FG


def bios_panel(content: Any, title: str, *, Panel: Any, box: Any) -> Any:
    box_style = getattr(box, "ASCII", getattr(box, "SQUARE", None))
    return Panel(
        content,
        title=f"[{STYLE_TITLE}] {title.upper()} [/]",
        border_style=STYLE_BORDER,
        style=STYLE_FG,
        box=box_style,
        padding=(0, 1),
    )


def bios_banner(Text: Any, title: str) -> Any:
    banner = Text()
    banner.append(f"{BIOS_VERSION}\n", style=STYLE_TITLE)
    banner.append(f"Copyright (C) {BIOS_VENDOR}\n", style=STYLE_DIM)
    banner.append("-" * 58 + "\n", style=STYLE_DIM)
    banner.append(title.upper(), style=STYLE_BOLD)
    return banner


def bios_hint(Text: Any) -> Any:
    return bios_text(Text, "F1=Help   F10=Save   ESC=Exit", style=STYLE_DIM)


def create_console(Console: Any) -> Any:
    return Console(highlight=False, force_terminal=True)
