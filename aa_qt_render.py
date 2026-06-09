"""Native Windows Qt appearance and CPU-side compute environment for Marktanalyse.exe."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_QT_NATIVE_BOOTSTRAPPED = False
_CPU_COMPUTE_CONFIGURED = False

# Windows 11 Fluent-inspired palette (light mode)
WIN11_BG = "#f3f3f3"
WIN11_CARD = "#ffffff"
WIN11_TEXT = "#202020"
WIN11_TEXT_SECONDARY = "#605e5c"
WIN11_ACCENT = "#0067c0"
WIN11_BORDER = "#e5e5e5"
WIN11_SUCCESS = "#107c10"
WIN11_ERROR = "#c42b1c"


def is_auto_run_mode() -> bool:
    """Fully unattended launcher flow (EXE default): no blocking popups, auto-close on success."""
    if os.environ.get("AA_NONINTERACTIVE", "").strip() == "1":
        return True
    if os.environ.get("AA_AUTO_RUN", "").strip() == "1":
        return True
    if os.environ.get("AA_AUTO_RUN", "").strip() == "0":
        return False
    return getattr(sys, "frozen", False)


def resolve_app_icon_path() -> Path | None:
    """Locate R3 icon for EXE, taskbar, and title bar."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "assets" / "marktanalyse_r3.ico")
        candidates.append(exe_dir / "Marktanalyse.ico")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "assets" / "marktanalyse_r3.ico")
        try:
            from aa_paths import project_root

            root = project_root()
            candidates.append(root / "assets" / "marktanalyse_r3.ico")
            candidates.append(root / "Marktanalyse.ico")
        except Exception:
            pass
    root = Path(__file__).resolve().parent
    candidates.append(root / "assets" / "marktanalyse_r3.ico")
    for path in candidates:
        if path.is_file():
            return path
    return None


_APP_ICON = None


def load_app_qicon() -> object | None:
    """Cached application icon from bundled .ico (never Python/PyInstaller default)."""
    global _APP_ICON
    if _APP_ICON is not None:
        return _APP_ICON
    path = resolve_app_icon_path()
    if path is None:
        return None
    try:
        from PySide6.QtGui import QIcon

        icon = QIcon(str(path))
        if icon.isNull():
            return None
        _APP_ICON = icon
        return icon
    except Exception:
        return None


def apply_app_icon(app: object) -> None:
    icon = load_app_qicon()
    if icon is None:
        return
    try:
        app.setWindowIcon(icon)
    except Exception:
        pass


def apply_window_icon(widget: object) -> None:
    icon = load_app_qicon()
    if icon is None:
        return
    try:
        widget.setWindowIcon(icon)
    except Exception:
        pass


def apply_native_taskbar_icon(widget: object) -> None:
    """Win32 WM_SETICON fallback so taskbar uses .ico instead of generic Python icon."""
    if sys.platform != "win32":
        return
    path = resolve_app_icon_path()
    if path is None:
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        if hwnd == 0:
            return
        LR_LOADFROMFILE = 0x00000010
        LR_DEFAULTSIZE = 0x00000040
        IMAGE_ICON = 1
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        hicon = ctypes.windll.user32.LoadImageW(
            0,
            str(path),
            IMAGE_ICON,
            0,
            0,
            LR_LOADFROMFILE | LR_DEFAULTSIZE,
        )
        if not hicon:
            return
        ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
        ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
    except Exception:
        pass


def configure_windows_app_identity() -> None:
    """Taskbar / Alt-Tab icon on Windows (avoids generic Python fallback)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        app_id = "ActiveAlpha.Marktanalyse.R3"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def bootstrap_qt_native_windows(*, force: bool = False) -> None:
    """Sharp native Windows widgets — avoid OpenGL/RHI overrides that blur QWidget text."""
    global _QT_NATIVE_BOOTSTRAPPED
    if _QT_NATIVE_BOOTSTRAPPED and not force:
        return

    for key in ("QT_OPENGL", "QSG_RHI_BACKEND", "QSG_RHI_PREFER_SOFTWARE_RENDERER"):
        os.environ.pop(key, None)

    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.Round
        )
    except Exception:
        pass

    _QT_NATIVE_BOOTSTRAPPED = True


bootstrap_qt_gpu_env = bootstrap_qt_native_windows


def win11_ui_font(*, size: int = 9, semibold: bool = False, display: bool = False) -> object:
    """Prefer Segoe UI with safe fallbacks (avoid missing Variable Text families)."""
    try:
        from PySide6.QtGui import QFont

        for family in ("Segoe UI", "Tahoma", "Arial"):
            font = QFont(family, size)
            if font.family():
                if semibold:
                    font.setWeight(QFont.Weight.DemiBold)
                return font
        font = QFont("Segoe UI", size)
        if semibold:
            font.setWeight(QFont.Weight.DemiBold)
        return font
    except Exception:
        return None


def configure_native_app_font(app: object) -> None:
    """Windows 11 body font (Segoe UI Variable)."""
    font = win11_ui_font(size=10)
    if font is not None:
        try:
            app.setFont(font)
        except Exception:
            pass


def time_value_font(*, size: int = 9) -> object | None:
    """Segoe UI clock line — same size as body text (Windows 11 settings style)."""
    return win11_ui_font(size=size, semibold=False)


def style_native_groupbox(box: object) -> None:
    try:
        box.setStyleSheet(
            f"QGroupBox {{"
            f"  font-family: 'Segoe UI', Tahoma, sans-serif;"
            f"  font-size: 11pt;"
            f"  font-weight: 600;"
            f"  color: {WIN11_TEXT};"
            f"  border: 1px solid {WIN11_BORDER};"
            f"  border-radius: 8px;"
            f"  margin-top: 14px;"
            f"  padding: 18px 14px 14px 14px;"
            f"  background-color: {WIN11_CARD};"
            f"}}"
            f"QGroupBox::title {{"
            f"  subcontrol-origin: margin;"
            f"  left: 14px;"
            f"  padding: 0 8px;"
            f"  color: {WIN11_TEXT};"
            f"}}"
        )
    except Exception:
        pass


def style_native_button(btn: object, *, primary: bool = False) -> None:
    try:
        bg = WIN11_ACCENT if primary else WIN11_CARD
        fg = "#ffffff" if primary else WIN11_TEXT
        border = WIN11_ACCENT if primary else WIN11_BORDER
        hover = "#005a9e" if primary else "#f5f5f5"
        btn.setMinimumHeight(34)
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  font-family: 'Segoe UI', Tahoma, sans-serif;"
            f"  font-size: 10pt;"
            f"  padding: 6px 16px;"
            f"  border: 1px solid {border};"
            f"  border-radius: 6px;"
            f"  background-color: {bg};"
            f"  color: {fg};"
            f"}}"
            f"QPushButton:hover {{ background-color: {hover}; }}"
            f"QPushButton:disabled {{ color: #a19f9d; background-color: #f0f0f0; border-color: {WIN11_BORDER}; }}"
        )
    except Exception:
        pass


def style_native_line_edit(field: object) -> None:
    try:
        field.setMinimumHeight(34)
        field.setStyleSheet(
            f"QLineEdit {{"
            f"  font-family: 'Segoe UI', Tahoma, sans-serif;"
            f"  font-size: 11pt;"
            f"  padding: 6px 10px;"
            f"  border: 1px solid {WIN11_BORDER};"
            f"  border-radius: 6px;"
            f"  background-color: {WIN11_CARD};"
            f"  color: {WIN11_TEXT};"
            f"}}"
            f"QLineEdit:focus {{ border: 1px solid {WIN11_ACCENT}; }}"
        )
    except Exception:
        pass


def style_native_table(table: object) -> None:
    try:
        table.setStyleSheet(
            f"QTableWidget {{"
            f"  font-family: 'Segoe UI', Tahoma, sans-serif;"
            f"  font-size: 10pt;"
            f"  background-color: {WIN11_CARD};"
            f"  border: 1px solid {WIN11_BORDER};"
            f"  border-radius: 8px;"
            f"  gridline-color: {WIN11_BORDER};"
            f"  alternate-background-color: #fafafa;"
            f"  selection-background-color: #e5f1fb;"
            f"  selection-color: {WIN11_TEXT};"
            f"}}"
            f"QHeaderView::section {{"
            f"  font-family: 'Segoe UI', Tahoma, sans-serif;"
            f"  font-size: 10pt;"
            f"  font-weight: 600;"
            f"  background-color: #fafafa;"
            f"  color: {WIN11_TEXT};"
            f"  padding: 10px 8px;"
            f"  border: none;"
            f"  border-bottom: 1px solid {WIN11_BORDER};"
            f"}}"
            f"QTableWidget::item {{ padding: 8px 6px; }}"
        )
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(36)
    except Exception:
        pass


def style_time_panel(frame: object) -> None:
    try:
        frame.setStyleSheet(
            f"QFrame#timePanel {{"
            f"  background-color: {WIN11_CARD};"
            f"  border: 1px solid {WIN11_BORDER};"
            f"  border-radius: 8px;"
            f"}}"
        )
    except Exception:
        pass


def apply_win11_surface(widget: object, *, kind: str = "window") -> None:
    """Background via palette — keeps text sharp on HiDPI."""
    try:
        from PySide6.QtGui import QColor, QPalette

        bg = WIN11_BG if kind == "window" else WIN11_CARD
        widget.setAutoFillBackground(True)
        palette = widget.palette()
        palette.setColor(widget.backgroundRole(), QColor(bg))
        widget.setPalette(palette)
        if kind == "log":
            palette.setColor(widget.foregroundRole(), QColor(WIN11_TEXT))
            widget.setPalette(palette)
    except Exception:
        pass


def configure_cpu_compute_env(*, launcher: bool = False) -> None:
    """Keep numerical / subprocess work on CPU threads."""
    global _CPU_COMPUTE_CONFIGURED
    if _CPU_COMPUTE_CONFIGURED and not launcher:
        return

    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    os.environ.setdefault("HIP_VISIBLE_DEVICES", "")
    os.environ.setdefault("MPLBACKEND", "Agg")

    if launcher or os.environ.get("AA_LAUNCHER_READY", "").strip() == "1":
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
        os.environ.setdefault("MKL_NUM_THREADS", "1")
        os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

    _CPU_COMPUTE_CONFIGURED = True


def apply_window_gpu_hints(widget: object) -> None:
    _ = widget


def apply_native_label_style(label: object, *, color: str, bold: bool = False) -> None:
    """Color/bold via palette+font — stylesheets blur QLabel text on Windows HiDPI."""
    try:
        from PySide6.QtGui import QColor, QFont, QPalette

        label.setStyleSheet("")
        font = QFont(label.font())
        font.setBold(bold)
        label.setFont(font)
        palette = label.palette()
        palette.setColor(label.foregroundRole(), QColor(color))
        label.setPalette(palette)
    except Exception:
        weight = "bold" if bold else "normal"
        label.setStyleSheet(f"color: {color}; font-weight: {weight};")


def style_native_progress_bar(bar: object) -> None:
    """Windows 11 accent progress bar."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont

        bar.setMinimumHeight(28)
        bar.setMaximumHeight(28)
        bar.setTextVisible(True)
        bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = win11_ui_font(size=9)
        if font is not None:
            bar.setFont(font)
        bar.setStyleSheet(
            "QProgressBar {"
            f"  border: 1px solid {WIN11_BORDER};"
            "  border-radius: 6px;"
            "  background-color: #ebebeb;"
            "  padding: 2px;"
            "  text-align: center;"
            "  color: #202020;"
            "}"
            "QProgressBar::chunk {"
            f"  background-color: {WIN11_ACCENT};"
            "  border-radius: 4px;"
            "}"
        )
    except Exception:
        pass
