from __future__ import annotations

import io
import sys

from aa_dashboard_qt import should_use_gui


class _Args:
    plain_progress = False
    no_gui = False
    gui = False


def test_should_use_gui_disabled_when_noninteractive(monkeypatch):
    monkeypatch.setenv("AA_NONINTERACTIVE", "1")
    if sys.stdout is None:
        monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    assert should_use_gui(_Args()) is False


def test_should_use_gui_disabled_when_stdout_not_tty(monkeypatch):
    monkeypatch.delenv("AA_NONINTERACTIVE", raising=False)
    monkeypatch.setenv("AA_GUI", "0")
    if sys.stdout is None:
        monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert should_use_gui(_Args()) is False
