"""X11-Hilfen ohne xdotool/xclip — python-xlib + tkinter."""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Dict, List, Optional


def xlib_available() -> bool:
    from analytics.terminal_runtime import bootstrap_graphical_env

    bootstrap_graphical_env()
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        from Xlib import display  # noqa: F401

        return True
    except Exception:
        return False


def _display():
    from Xlib import display

    return display.Display()


_KEY_ALIASES = {
    "ctrl": "Control_L",
    "control": "Control_L",
    "shift": "Shift_L",
    "alt": "Alt_L",
    "meta": "Super_L",
    "super": "Super_L",
    "return": "Return",
    "enter": "Return",
    "tab": "Tab",
    "escape": "Escape",
    "esc": "Escape",
    "down": "Down",
    "up": "Up",
    "left": "Left",
    "right": "Right",
}


def _resolve_keysym(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return "Return"
    if len(raw) == 1:
        return raw
    return _KEY_ALIASES.get(raw.lower(), raw)


def press_key(key_name: str = "Return") -> Dict[str, Any]:
    from analytics.terminal_runtime import bootstrap_graphical_env

    bootstrap_graphical_env()
    try:
        from Xlib import X, XK
        from Xlib.ext import xtest

        d = _display()
        sym_name = _resolve_keysym(key_name)
        keysym = getattr(XK, f"XK_{sym_name}", None)
        if keysym is None and len(sym_name) == 1:
            keysym = ord(sym_name)
        if keysym is None:
            keysym = XK.XK_Return
        keycode = d.keysym_to_keycode(keysym)
        xtest.fake_input(d, X.KeyPress, keycode)
        d.sync()
        xtest.fake_input(d, X.KeyRelease, keycode)
        d.sync()
        return {"ok": True, "detail_de": f"Xlib key {key_name}"}
    except Exception as exc:
        return {"ok": False, "detail_de": f"Xlib key: {exc}"[:120]}


def _decode_wm_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (list, tuple)):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)


def _window_title(w: Any, d: Any) -> str:
    from Xlib import X

    for atom_name in ("_NET_WM_VISIBLE_NAME", "_NET_WM_NAME"):
        prop = w.get_full_property(d.intern_atom(atom_name), 0)
        if prop and prop.value is not None:
            title = _decode_wm_value(prop.value).strip()
            if title:
                return title
    prop = w.get_full_property(X.WM_NAME, X.AnyPropertyType)
    if prop and prop.value is not None:
        return _decode_wm_value(prop.value).strip()
    return ""


def list_window_titles() -> List[str]:
    from analytics.terminal_runtime import bootstrap_graphical_env

    bootstrap_graphical_env()
    titles: List[str] = []
    try:
        from Xlib import X

        d = _display()
        root = d.screen().root
        prop = root.get_full_property(d.intern_atom("_NET_CLIENT_LIST"), X.AnyPropertyType)
        if not prop or prop.value is None:
            return titles
        for wid in prop.value:
            w = d.create_resource_object("window", wid)
            title = _window_title(w, d)
            if title:
                titles.append(title)
    except Exception:
        return titles
    return titles


def activate_window(name_part: str) -> Dict[str, Any]:
    from analytics.terminal_runtime import bootstrap_graphical_env

    bootstrap_graphical_env()
    try:
        from Xlib import X

        d = _display()
        root = d.screen().root
        prop = root.get_full_property(d.intern_atom("_NET_CLIENT_LIST"), X.AnyPropertyType)
        if not prop or prop.value is None:
            return {"ok": False, "detail_de": f"Keine Fensterliste: {name_part}"}
        needle = name_part.lower()
        for wid in prop.value:
            w = d.create_resource_object("window", wid)
            title = _window_title(w, d)
            if title and needle in title.lower():
                w.set_input_focus(X.RevertToParent, X.CurrentTime)
                w.raise_window()
                d.sync()
                return {"ok": True, "detail_de": title[:80], "window": title}
        return {"ok": False, "detail_de": f"Fenster nicht gefunden: {name_part}"}
    except Exception as exc:
        return {"ok": False, "detail_de": f"Xlib window: {exc}"[:120]}


def press_hotkey(*keys: str) -> Dict[str, Any]:
    from analytics.terminal_runtime import bootstrap_graphical_env, graphical_env_dict

    bootstrap_graphical_env()
    if not keys:
        return {"ok": False, "detail_de": "Hotkey leer"}
    if shutil_which("xdotool"):
        combo = "+".join(_resolve_keysym(k) for k in keys)
        try:
            proc = subprocess.run(
                ["xdotool", "key", "--clearmodifiers", combo],
                env=graphical_env_dict(),
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            return {
                "ok": proc.returncode == 0,
                "detail_de": f"xdotool {combo}",
                "tool": "xdotool",
            }
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "detail_de": str(exc)[:120]}
    try:
        from Xlib import X, XK
        from Xlib.ext import xtest

        d = _display()
        resolved = [_resolve_keysym(k) for k in keys]
        mod_names = {"Control_L", "Shift_L", "Alt_L", "Super_L"}
        mods = [r for r in resolved if r in mod_names]
        mains = [r for r in resolved if r not in mod_names]
        for mod in mods:
            xtest.fake_input(d, X.KeyPress, d.keysym_to_keycode(getattr(XK, f"XK_{mod}")))
        for main in mains or ["Return"]:
            sym = getattr(XK, f"XK_{main}", None)
            if sym is None and len(main) == 1:
                sym = ord(main)
            if sym is None:
                sym = XK.XK_Return
            code = d.keysym_to_keycode(sym)
            xtest.fake_input(d, X.KeyPress, code)
            xtest.fake_input(d, X.KeyRelease, code)
        for mod in reversed(mods):
            xtest.fake_input(d, X.KeyRelease, d.keysym_to_keycode(getattr(XK, f"XK_{mod}")))
        d.sync()
        return {"ok": True, "detail_de": "xlib hotkey", "tool": "xlib"}
    except Exception as exc:
        return {"ok": False, "detail_de": f"xlib hotkey: {exc}"[:120]}


def type_text(text: str, *, delay_ms: int = 15) -> Dict[str, Any]:
    from analytics.terminal_runtime import bootstrap_graphical_env, graphical_env_dict

    bootstrap_graphical_env()
    payload = str(text or "")
    if not payload:
        return {"ok": False, "detail_de": "Text leer"}
    if shutil_which("xdotool"):
        try:
            proc = subprocess.run(
                ["xdotool", "type", "--delay", str(delay_ms), "--", payload],
                env=graphical_env_dict(),
                capture_output=True,
                text=True,
                timeout=max(12, len(payload) // 4),
                check=False,
            )
            return {
                "ok": proc.returncode == 0,
                "detail_de": "xdotool type",
                "tool": "xdotool",
            }
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "detail_de": str(exc)[:120]}
    steps: List[Dict[str, Any]] = []
    for ch in payload:
        ret = press_key(ch)
        steps.append(ret)
        if not ret.get("ok"):
            return {"ok": False, "detail_de": ret.get("detail_de"), "steps": steps}
    return {"ok": True, "detail_de": "xlib type", "tool": "xlib", "steps": steps}


def attach_zip_dialog(zip_path: str, *, menu_delay_s: float = 0.6) -> Dict[str, Any]:
    """WhatsApp Web: Anhang-Menü → Dokument → Dateidialog."""
    import time
    from pathlib import Path

    path = str(Path(zip_path).resolve())
    if not Path(path).is_file():
        return {"ok": False, "detail_de": f"ZIP fehlt: {path}"}
    steps: List[Dict[str, Any]] = []
    time.sleep(max(0.4, menu_delay_s))
    for action, arg in (
        ("hotkey", ("shift", "Tab")),
        ("key", "Return"),
        ("key", "Return"),
        ("sleep", 1.0),
        ("hotkey", ("ctrl", "l")),
        ("clipboard", path),
        ("hotkey", ("ctrl", "v")),
        ("key", "Return"),
        ("sleep", 0.8),
        ("key", "Return"),
    ):
        if action == "sleep":
            time.sleep(float(arg))
            continue
        if action == "clipboard":
            clip = copy_clipboard(str(arg))
            steps.append({"kind": "clipboard_path", **clip})
            if not clip.get("ok"):
                typed = type_text(str(arg))
                steps.append({"kind": "type_path", **typed})
                if not typed.get("ok"):
                    return {"ok": False, "detail_de": "ZIP-Pfad nicht eingefügt", "steps": steps}
            continue
        if action == "hotkey":
            ret = press_hotkey(*arg)
        else:
            ret = press_key(str(arg))
        steps.append({"kind": action, **ret})
        if not ret.get("ok"):
            return {"ok": False, "detail_de": ret.get("detail_de") or f"{action} fehlgeschlagen", "steps": steps}
    return {"ok": True, "detail_de": "ZIP im Dateidialog ausgewählt", "steps": steps, "zip_auto": True}


def send_return_blind(*, presses: int = 2, delay_s: float = 0.4) -> Dict[str, Any]:
    import time

    steps: List[Dict[str, Any]] = []
    ok = False
    for _ in range(max(1, presses)):
        key = press_key("Return")
        steps.append({"kind": "blind_return", **key})
        ok = ok or bool(key.get("ok"))
        time.sleep(max(0.1, delay_s))
    return {
        "ok": ok,
        "detail_de": "Return blind (Vordergrund)" if ok else "Return blind fehlgeschlagen",
        "steps": steps,
    }


def send_return_to_window(*patterns: str) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    for pat in patterns:
        act = activate_window(pat)
        steps.append({"kind": "activate", "pattern": pat, **act})
        if act.get("ok"):
            key = press_key("Return")
            steps.append({"kind": "return", **key})
            if key.get("ok"):
                return {"ok": True, "detail_de": f"Return an {pat}", "steps": steps}
    blind = send_return_blind(presses=2)
    steps.extend(blind.get("steps") or [])
    if blind.get("ok"):
        return {"ok": True, "detail_de": blind.get("detail_de"), "steps": steps}
    titles = list_window_titles()
    if titles:
        steps.append({"kind": "window_titles", "titles": titles[:12]})
    return {"ok": False, "detail_de": "Kein Fenster für Return", "steps": steps}


def copy_clipboard(text: str) -> Dict[str, Any]:
    from analytics.terminal_runtime import bootstrap_graphical_env, graphical_env_dict

    bootstrap_graphical_env()
    env = graphical_env_dict()
    payload = str(text or "")
    if not payload.strip():
        return {"ok": False, "detail_de": "Text leer"}
    for args in (
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["xsel", "-b", "-i"],
    ):
        if not shutil_which(args[0]):
            continue
        try:
            subprocess.run(args, input=payload.encode("utf-8"), check=False, timeout=4, env=env)
            return {"ok": True, "detail_de": args[0], "tool": args[0]}
        except (OSError, subprocess.TimeoutExpired):
            continue
    try:
        code = (
            "import tkinter as tk\n"
            "r=tk.Tk(); r.withdraw()\n"
            "r.clipboard_clear(); r.clipboard_append(" + repr(payload) + ")\n"
            "r.update(); r.destroy()\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=6, check=False)
        if proc.returncode == 0:
            return {"ok": True, "detail_de": "tkinter(subprocess)", "tool": "tkinter"}
    except (OSError, subprocess.TimeoutExpired):
        pass
    if xlib_available():
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(payload)
            root.update()
            root.destroy()
            return {"ok": True, "detail_de": "tkinter", "tool": "tkinter"}
        except Exception:
            pass
    return {"ok": False, "detail_de": "Clipboard fehlgeschlagen"}


def shutil_which(cmd: str) -> Optional[str]:
    import shutil

    return shutil.which(cmd)
