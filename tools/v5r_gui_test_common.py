"""Shared Win32 helpers for V5R GUI runtime evidence scripts."""
from __future__ import annotations

import ctypes
import subprocess
from ctypes import wintypes


def marktanalyse_pids() -> list[int]:
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-Process -Name Marktanalyse -ErrorAction SilentlyContinue).Id -join ' '",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return [int(x) for x in (proc.stdout or "").split() if x.strip().isdigit()]


def process_responding(pid: int) -> bool:
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).Responding"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "True" in (proc.stdout or "")


def process_main_window_title(pid: int) -> str:
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).MainWindowTitle",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "").strip()


def find_window_for_pids(pids: set[int], title_fragment: str) -> tuple[int | None, str]:
    for pid in sorted(pids):
        title = process_main_window_title(pid)
        if title and (not title_fragment or title_fragment.lower() in title.lower()):
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).MainWindowHandle",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            handle_text = (proc.stdout or "").strip()
            if handle_text.isdigit() and int(handle_text) > 0:
                return int(handle_text), title
    user32 = ctypes.windll.user32
    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _enum(hwnd, _lparam):
        proc_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
        if int(proc_id.value) not in pids:
            return True
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(max(length + 1, 256))
        user32.GetWindowTextW(hwnd, buf, 256)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == "IME":
            return True
        title = buf.value or ""
        if title or cls.value:
            found.append((int(hwnd), title or cls.value))
        return True

    user32.EnumWindows(_enum, 0)
    if not found:
        return None, ""
    for hwnd, title in found:
        if title_fragment.lower() in title.lower():
            return hwnd, title
    return found[0][0], found[0][1]


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def capture_window_png(hwnd: int, out_path) -> bool:
    try:
        from PIL import ImageGrab
    except ImportError:
        return False
    left, top, right, bottom = window_rect(hwnd)
    if right <= left or bottom <= top:
        return False
    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    img.save(out_path)
    return out_path.is_file() and out_path.stat().st_size > 0


def stop_marktanalyse_processes() -> bool:
    pids = marktanalyse_pids()
    for pid in pids:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
            check=False,
        )
    return len(marktanalyse_pids()) == 0
