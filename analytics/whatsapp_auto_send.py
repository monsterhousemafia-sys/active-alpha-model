"""WhatsApp Auto-Send ohne Docker/WAHA — Playwright (voll) oder xdotool (Text)."""
from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_EVIDENCE_REL = Path("evidence/whatsapp_auto_send_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def _session_dir(root: Path, cfg: Dict[str, Any]) -> Path:
    rel = str(cfg.get("playwright_session_dir") or "control/secrets/whatsapp_playwright")
    return (Path(root) / rel).resolve()


def firefox_profile_dir(root: Path, cfg: Dict[str, Any]) -> Path:
    rel = str(cfg.get("firefox_profile_dir") or "control/secrets/whatsapp_firefox_profile")
    return (Path(root) / rel).resolve()


_FIREFOX_SKIP_PREFS = (
    'user_pref("browser.aboutwelcome.enabled", false);',
    'user_pref("trailhead.firstrun.didSeeAboutWelcome", true);',
    'user_pref("datareporting.policy.dataSubmissionPolicyBypassNotification", true);',
    'user_pref("datareporting.policy.dataSubmissionPolicyAcceptedVersion", 2);',
    'user_pref("termsofuse.bypassNotification", true);',
    'user_pref("browser.startup.homepage_override.mstone", "ignore");',
    'user_pref("startup.homepage_welcome_url", "");',
    'user_pref("startup.homepage_welcome_url.additional", "");',
    'user_pref("browser.laterrun.enabled", false);',
    'user_pref("browser.shell.checkDefaultBrowser", false);',
    'user_pref("browser.rights.3.shown", true);',
)


def bootstrap_firefox_profile(profile: Path) -> Dict[str, Any]:
    profile = Path(profile)
    profile.mkdir(parents=True, exist_ok=True)
    user_js = profile / "user.js"
    user_js.write_text("\n".join(_FIREFOX_SKIP_PREFS) + "\n", encoding="utf-8")
    dist = profile / "distribution"
    dist.mkdir(parents=True, exist_ok=True)
    policies = {
        "policies": {
            "SkipTermsOfUse": True,
            "OverrideFirstRunPage": "",
            "OverridePostUpdatePage": "",
            "UserMessaging": {"SkipOnboarding": True},
        }
    }
    (dist / "policies.json").write_text(json.dumps(policies, indent=2), encoding="utf-8")
    return {"ok": True, "profile": str(profile), "detail_de": "Firefox-Profil ohne Datenschutz-Popup"}


def _firefox_cmd(root: Path, cfg: Dict[str, Any], url: str) -> List[str]:
    browser = _firefox_binary()
    if not browser:
        return []
    profile = firefox_profile_dir(root, cfg)
    bootstrap_firefox_profile(profile)
    return [browser, "-no-remote", "-profile", str(profile), url]


def _send_open_url(phone: str, text: str, *, with_zip: bool) -> str:
    query = urllib.parse.quote(text)
    if with_zip:
        return f"https://web.whatsapp.com/send?phone={phone}&text={query}"
    from analytics.whatsapp_spread import build_wa_me_url

    return build_wa_me_url(phone, text) or f"https://web.whatsapp.com/send?phone={phone}&text={query}"


def _launch_firefox_send_url(
    root: Path,
    cfg: Dict[str, Any],
    phone: str,
    text: str,
    *,
    with_zip: bool = False,
) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    url = _send_open_url(phone, text, with_zip=with_zip)
    cmd = _firefox_cmd(root, cfg, url)
    steps: List[Dict[str, Any]] = []
    if not cmd:
        opener = _run_opener(url)
        steps.append({"kind": "open", **opener})
        if not opener.get("ok"):
            return steps, {"ok": False, "detail_de": "Firefox/Web-WhatsApp nicht geöffnet"}
        return steps, None
    try:
        from analytics.terminal_runtime import graphical_env_dict

        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=graphical_env_dict())
        steps.append({"kind": "firefox_profile", "ok": True, "profile": str(firefox_profile_dir(root, cfg))})
        return steps, None
    except OSError as exc:
        return steps, {"ok": False, "detail_de": str(exc)}


def _attach_zip_after_send(
    zip_path: Path,
    *,
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    if not cfg.get("zip_attach_auto", True):
        return {"ok": False, "detail_de": "zip_attach_auto=false", "zip_auto": False}
    path = Path(zip_path)
    if not path.is_file():
        return {"ok": False, "detail_de": "ZIP fehlt", "zip_auto": False}
    steps: List[Dict[str, Any]] = []
    if xdotool_available():
        try:
            for pat in ("WhatsApp", "whatsapp", "Firefox", "Mozilla"):
                proc = subprocess.run(
                    ["xdotool", "search", "--name", pat, "windowactivate", "--sync"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if proc.returncode == 0:
                    steps.append({"kind": "activate", "ok": True, "pattern": pat})
                    break
            from analytics.x11_send import attach_zip_dialog

            attach = attach_zip_dialog(str(path))
            steps.extend(attach.get("steps") or [])
            return {**attach, "engine": "xdotool", "steps": steps}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "detail_de": str(exc)[:120], "zip_auto": False, "steps": steps}
    from analytics.x11_send import attach_zip_dialog, xlib_available

    if xlib_available():
        attach = attach_zip_dialog(str(path))
        steps.extend(attach.get("steps") or [])
        return {**attach, "engine": "xlib", "steps": steps}
    return {"ok": False, "detail_de": "ZIP-Anhang: xlib/xdotool fehlt", "zip_auto": False, "steps": steps}


def _send_enter_and_zip(
    steps: List[Dict[str, Any]],
    *,
    zip_path: Optional[Path],
    engine: str,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from analytics.x11_send import send_return_to_window, xlib_available

    if xdotool_available():
        for name_pat in ("WhatsApp", "whatsapp", "Firefox", "Mozilla"):
            try:
                proc = subprocess.run(
                    ["xdotool", "search", "--name", name_pat, "windowactivate", "--sync", "key", "Return"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                if proc.returncode == 0:
                    steps.append({"kind": "enter", "ok": True, "detail_de": f"xdotool Return ({name_pat})"})
                    break
            except (OSError, subprocess.TimeoutExpired):
                continue
    elif xlib_available():
        ret = send_return_to_window("WhatsApp", "whatsapp", "Firefox", "Mozilla")
        steps.append({"kind": "xlib_send", **ret})
        if not ret.get("ok"):
            return {"ok": False, "engine": engine, "detail_de": ret.get("detail_de"), "steps": steps}
    else:
        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            pyautogui.press("enter")
            steps.append({"kind": "enter", "ok": True, "detail_de": "pyautogui Return"})
        except Exception as exc:
            return {"ok": False, "engine": engine, "detail_de": str(exc)[:120], "steps": steps}

    zip_auto = False
    zip_note = ""
    if zip_path and zip_path.is_file():
        attach = _attach_zip_after_send(zip_path, cfg=cfg or {})
        steps.append({"kind": "zip_attach", **attach})
        zip_auto = bool(attach.get("ok"))
        if zip_auto:
            zip_note = " — ZIP automatisch angehängt"
        else:
            zip_open = _run_opener(str(zip_path))
            steps.append({"kind": "zip_open", **zip_open})
            zip_note = " — ZIP geöffnet, einmal anhängen falls nötig"
    return {
        "ok": True,
        "engine": engine,
        "detail_de": f"Text gesendet (Enter){zip_note}",
        "steps": steps,
        "zip_auto": zip_auto,
    }


def _dismiss_firefox_privacy(*, wait_s: float = 2.0) -> Dict[str, Any]:
    from analytics.x11_send import activate_window, press_key, xlib_available

    steps: List[Dict[str, Any]] = []
    time.sleep(max(1.0, wait_s))
    if xdotool_available():
        for seq in (
            ["key", "Tab", "Tab", "Return"],
            ["key", "Return"],
            ["key", "Escape"],
        ):
            try:
                proc = subprocess.run(
                    ["xdotool", "search", "--name", "Firefox", "windowactivate", "--sync", *seq],
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                )
                if proc.returncode == 0:
                    steps.append({"kind": "xdotool_privacy", "ok": True, "seq": seq})
                    return {"ok": True, "detail_de": "Datenschutz geklickt (xdotool)", "steps": steps}
            except (OSError, subprocess.TimeoutExpired):
                continue
    if xlib_available():
        activate_window("Firefox")
        for key in ("Tab", "Tab", "Return", "Return"):
            ret = press_key(key)
            steps.append({"kind": "xlib_privacy", "key": key, **ret})
            if not ret.get("ok"):
                return {"ok": False, "detail_de": ret.get("detail_de") or "xlib privacy", "steps": steps}
            time.sleep(0.25)
        return {"ok": True, "detail_de": "Datenschutz geklickt (xlib)", "steps": steps}
    if pyautogui_available():
        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            for _ in range(4):
                pyautogui.press("tab")
            pyautogui.press("enter")
            time.sleep(1.0)
            pyautogui.press("enter")
            steps.append({"kind": "pyautogui_privacy", "ok": True})
            return {"ok": True, "detail_de": "Datenschutz geklickt (Tab+Enter)", "steps": steps}
        except Exception as exc:
            return {"ok": False, "detail_de": f"Privacy-Dismiss: {exc}", "steps": steps}
    return {"ok": False, "detail_de": "Privacy-Dismiss: keine Engine", "steps": steps}


def playwright_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def xdotool_available() -> bool:
    from analytics.terminal_runtime import bootstrap_graphical_env

    bootstrap_graphical_env()
    import os

    return _which("xdotool") is not None and bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def pyautogui_available() -> bool:
    from analytics.terminal_runtime import bootstrap_graphical_env

    bootstrap_graphical_env()
    import os

    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    if not _firefox_binary():
        return False
    try:
        import pyautogui  # noqa: F401

        return True
    except (ImportError, SystemExit, Exception):
        return False


def _firefox_binary() -> Optional[str]:
    for name in ("firefox", "firefox-esr", "chromium", "chromium-browser", "google-chrome"):
        path = _which(name)
        if path:
            return path
    return None


def auto_send_capabilities(root: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    from analytics.x11_send import xlib_available

    prof = firefox_profile_dir(root, cfg)
    return {
        "playwright": playwright_available(),
        "xlib": xlib_available(),
        "xdotool": xdotool_available(),
        "pyautogui": pyautogui_available(),
        "firefox": _firefox_binary(),
        "firefox_profile": str(prof),
        "firefox_profile_ready": (prof / "user.js").is_file(),
        "session_dir": str(_session_dir(root, cfg)),
        "session_exists": _session_dir(root, cfg).is_dir() and any(_session_dir(root, cfg).iterdir()),
    }


def _persist(root: Path, doc: Dict[str, Any]) -> Dict[str, Any]:
    from aa_safe_io import atomic_write_json

    doc["updated_at_utc"] = _utc_now()
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def _try_x11_send(
    root: Path,
    cfg: Dict[str, Any],
    phone: str,
    text: str,
    *,
    zip_path: Optional[Path],
    wait_s: float,
    engine: str = "x11",
) -> Dict[str, Any]:
    from analytics.x11_send import xlib_available

    if not xdotool_available() and not xlib_available() and not pyautogui_available():
        return {"ok": False, "engine": engine, "detail_de": "x11/xdotool/pyautogui nicht verfügbar"}
    steps, err = _launch_firefox_send_url(root, cfg, phone, text, with_zip=bool(zip_path and zip_path.is_file()))
    if err:
        return {"ok": False, "engine": engine, "steps": steps, **err}
    privacy = _dismiss_firefox_privacy(wait_s=3.0)
    steps.append({"kind": "privacy_dismiss", **privacy})
    time.sleep(max(18.0, wait_s))
    used = "xdotool" if xdotool_available() else ("xlib" if xlib_available() else "pyautogui")
    return _send_enter_and_zip(steps, zip_path=zip_path, engine=used, cfg=cfg)


def _try_playwright_send(
    root: Path,
    phone: str,
    text: str,
    *,
    zip_path: Optional[Path],
    cfg: Dict[str, Any],
    timeout_s: float = 90.0,
) -> Dict[str, Any]:
    if not playwright_available():
        return {"ok": False, "engine": "playwright", "detail_de": "pip install playwright && playwright install chromium"}
    profile = firefox_profile_dir(root, cfg)
    bootstrap_firefox_profile(profile)
    session = profile
    session.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "engine": "playwright", "detail_de": "playwright Import fehlgeschlagen"}

    query = urllib.parse.quote(text)
    url = f"https://web.whatsapp.com/send?phone={phone}&text={query}"
    steps: List[Dict[str, Any]] = []
    firefox_bin = _firefox_binary()
    try:
        with sync_playwright() as p:
            if firefox_bin:
                context = p.firefox.launch_persistent_context(
                    user_data_dir=str(session),
                    headless=False,
                    executable_path=firefox_bin,
                )
            else:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(session),
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"],
                )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
            page.wait_for_timeout(3000)
            for label in ("Accept", "Akzeptieren", "Agree", "Weiter", "OK"):
                btn = page.locator(f'button:has-text("{label}")')
                if btn.count() > 0:
                    btn.first.click(timeout=3000)
                    steps.append({"kind": "privacy_click", "ok": True, "label": label})
                    page.wait_for_timeout(1500)
                    break
            if page.locator('canvas[aria-label*="QR"]').count() > 0:
                return {
                    "ok": False,
                    "engine": "playwright",
                    "detail_de": "QR-Scan nötig — bash tools/setup_whatsapp_auto.sh auth",
                    "steps": steps,
                }
            page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
            page.wait_for_timeout(2500)
            send = page.locator('button[data-tab="11"], button[aria-label="Send"], span[data-icon="send"]')
            if send.count() > 0:
                send.first.click(timeout=5000)
                steps.append({"kind": "send_click", "ok": True})
            else:
                page.keyboard.press("Enter")
                steps.append({"kind": "send_enter", "ok": True})
            if zip_path and zip_path.is_file():
                attach = page.locator('button[title="Attach"], span[data-icon="attach-menu-plus"], div[title="Attach"]')
                if attach.count() > 0:
                    attach.first.click(timeout=5000)
                    page.wait_for_timeout(800)
                    doc_btn = page.locator('button:has-text("Document"), span:has-text("Document"), li:has-text("Document")')
                    if doc_btn.count() > 0:
                        with page.expect_file_chooser(timeout=8000) as fc_info:
                            doc_btn.first.click()
                        fc_info.value.set_files(str(zip_path))
                        page.wait_for_timeout(1200)
                        send2 = page.locator('button[data-tab="11"], button[aria-label="Send"], span[data-icon="send"]')
                        if send2.count() > 0:
                            send2.first.click(timeout=5000)
                        steps.append({"kind": "zip_attach", "ok": True, "path": str(zip_path)})
            page.wait_for_timeout(1500)
            context.close()
        return {
            "ok": True,
            "engine": "playwright",
            "detail_de": "Text + ZIP automatisch gesendet",
            "steps": steps,
            "zip_auto": bool(zip_path and zip_path.is_file()),
        }
    except Exception as exc:
        return {
            "ok": False,
            "engine": "playwright",
            "detail_de": f"Playwright: {str(exc)[:160]}",
            "steps": steps,
        }


def _run_opener(target: str) -> Dict[str, Any]:
    for cmd in (["xdg-open", target], ["gio", "open", target]):
        if not _which(cmd[0]):
            continue
        try:
            subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            return {"ok": True, "detail_de": f"{cmd[0]} ok", "target": target}
        except (OSError, subprocess.TimeoutExpired):
            continue
    return {"ok": False, "detail_de": "xdg-open fehlt", "target": target}


def auto_send_self(
    root: Path,
    *,
    phone: str,
    text: str,
    zip_path: Optional[Path],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    root = Path(root)
    mode = str(cfg.get("auto_send_mode") or "auto").strip().lower()
    wait_s = float(cfg.get("ui_wait_seconds") or 12)

    if mode == "manual":
        return {"ok": False, "skipped": True, "detail_de": "auto_send_mode=manual"}

    engines: List[str]
    if mode == "playwright":
        engines = ["playwright"]
    elif mode in {"xdotool", "x11", "pyautogui"}:
        engines = ["x11"]
    else:
        engines = ["x11", "playwright"]

    bootstrap_firefox_profile(firefox_profile_dir(root, cfg))
    attempts: List[Dict[str, Any]] = []
    for engine in engines:
        if engine == "playwright":
            result = _try_playwright_send(root, phone, text, zip_path=zip_path, cfg=cfg)
        else:
            result = _try_x11_send(root, cfg, phone, text, zip_path=zip_path, wait_s=wait_s)
        attempts.append(result)
        if result.get("ok"):
            doc = {
                "ok": True,
                "engine": result.get("engine"),
                "detail_de": result.get("detail_de"),
                "attempts": attempts,
                "zip_auto": result.get("zip_auto"),
            }
            return _persist(root, doc)

    doc = {
        "ok": False,
        "detail_de": "Auto-Send fehlgeschlagen — Fallback manuell",
        "attempts": attempts,
        "setup_de": "bash tools/setup_whatsapp_auto.sh",
    }
    return _persist(root, doc)
