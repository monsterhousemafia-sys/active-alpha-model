"""Hub-Seite: Shell-JS darf bei HTML-Render-Fehler nicht verschwinden."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from analytics.gui_preview_visual import render_gui_preview_html


def test_hub_page_script_parses_without_duplicate_icons() -> None:
    root = Path(__file__).resolve().parents[1]
    from analytics.preview_hub_page import render_hub_launch_page

    html = render_hub_launch_page(root).decode("utf-8")
    import re

    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    js = "\n".join(scripts)
    assert "const R3_ICON_MAP" not in js
    assert "window.R3_ICON_MAP" in js
    assert js.count("window._r3IconsReady") >= 2


def test_shell_js_survives_shell_html_render_failure() -> None:
    root = Path(__file__).resolve().parents[1]
    report = {"system_status": {}, "mode": "test"}
    with patch(
        "analytics.r3_ubuntu_shell.render_ubuntu_shell_section",
        side_effect=RuntimeError("shell html boom"),
    ):
        html = render_gui_preview_html(report)
    assert "r3NativeOpen" in html
    assert "r3-native-win" in html
    assert "shell html boom" not in html
