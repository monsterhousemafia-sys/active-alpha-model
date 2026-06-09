"""R3 Desktop OS — ersetzt Active-Alpha-Desktop-Spuren vollständig."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

_CONFIG_REL = Path("control/r3_desktop_os.json")
_ICON_REL = Path("assets/r3-os-icon.svg")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_desktop_os(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _CONFIG_REL)
    return doc or {
        "os_name": "R3",
        "os_full_de": "R3 — Research Operating System",
        "tagline_de": "Ein Kern. Ein Cockpit. Dein Desktop.",
    }


def _home() -> Path:
    return Path.home()


def _desktop_entry(
    *,
    name: str,
    comment: str,
    exec_line: str,
    path: Path,
    icon: str,
    categories: str,
    keywords: str,
    autostart: bool = False,
    delay: int = 0,
    wm_class: str = "R3",
    hidden_from_menus: bool = False,
    no_display: bool = False,
) -> str:
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        f"Name={name}",
        f"Comment={comment}",
        f"Exec={exec_line}",
        f"Path={path}",
        f"Icon={icon}",
        "Terminal=false",
        f"Categories={categories}",
        f"Keywords={keywords};",
        f"StartupWMClass={wm_class}",
    ]
    if autostart:
        lines.extend(
            [
                f"Hidden={'true' if hidden_from_menus else 'false'}",
                f"NoDisplay={'true' if no_display else 'false'}",
                "X-GNOME-Autostart-enabled=true",
                f"X-GNOME-Autostart-Delay={delay}",
                "StartupNotify=false",
            ]
        )
    return "\n".join(lines) + "\n"


def _local_apps_purged(root: Path) -> bool:
    manifest = _load_json(Path(root) / "control/local_apps_manifest.json")
    return str(manifest.get("status") or "").upper() in ("PURGED", "EXEC_MIRROR_ONLY")


def install_desktop_os(root: Path, *, force: bool = False) -> Dict[str, Any]:
    """Desktop, Autostart und Befehle — blockiert wenn Lokal-Apps PURGED."""
    root = Path(root).resolve()
    if _local_apps_purged(root) and not force:
        disposition = _load_json(root / "control/r3_pc_app_disposition.json")
        return {
            "ok": False,
            "blocked": True,
            "error": "LOCAL_APPS_PURGED",
            "headline_de": "Lokal-Apps deinstalliert — nur technische Exekutive",
            "message_de": (
                "Re-Install blockiert. Hub: python3 tools/preview_hub.py · "
                "Disposition: control/r3_pc_app_disposition.json"
            ),
            "functional_de": disposition.get("functional_technical_executive_de") or [],
            "purge_command_de": disposition.get("purge_command_de"),
        }
    cfg = load_desktop_os(root)
    growth: Dict[str, Any] = {}
    runtime_wm = "R3"
    agent_wm = "AlphaModelAgent"
    default_os_name = "R3"
    try:
        from analytics.alpha_model_growth import load_growth_config, product_name as growth_product_name, wm_class

        growth = load_growth_config(root)
        agent_wm = wm_class(root, "agent_chamber")
        default_os_name = growth_product_name(root)
    except Exception:
        pass
    try:
        from analytics.r3_os_supremacy import load_supremacy

        runtime_wm = str(load_supremacy(root).get("session", {}).get("wm_class") or runtime_wm)
    except Exception:
        pass

    os_name = str(cfg.get("os_name") or default_os_name)
    full = str(cfg.get("os_full_de") or f"{os_name} — Quantitative Decision Cockpit")
    tagline = str(cfg.get("tagline_de") or "")
    from analytics.r3_paths import migrate_legacy_share, r3_share_dir

    migrate_legacy_share()
    share_rel = str(cfg.get("share_dir") or ".local/share/r3-os")
    share = r3_share_dir()
    apps = _home() / ".local/share/applications"
    autostart = Path(os.environ.get("XDG_CONFIG_HOME", _home() / ".config")) / "autostart"
    bin_dir = _home() / ".local/bin"
    icons = _home() / ".local/share/icons/hicolor/scalable/apps"
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path("python3")

    for d in (share, apps, autostart, bin_dir, icons):
        d.mkdir(parents=True, exist_ok=True)

    icon_name = str(cfg.get("icon") or "r3-os")
    icon_dest = icons / f"{icon_name}.svg"
    try:
        from analytics.r3_desktop_icon import install_r3_desktop_icons

        install_r3_desktop_icons(root, icon_name=icon_name)
    except Exception:
        icon_src = root / _ICON_REL
        if icon_src.is_file():
            shutil.copy2(icon_src, icon_dest)

    removed: List[str] = []
    for legacy in cfg.get("remove_legacy_desktop_ids") or []:
        for base in (autostart, apps, root):
            p = Path(base) / str(legacy)
            if p.is_file():
                p.unlink()
                removed.append(str(p))

    cmds = dict(cfg.get("bin_commands") or {})
    shell_bins: Dict[str, str] = {}
    try:
        from analytics.r3_ubuntu_shell import load_ubuntu_shell

        shell_cfg = load_ubuntu_shell(root)
        for cmd, fid in (shell_cfg.get("quick_bin_commands") or {}).items():
            shell_bins[str(cmd)] = str(fid)
    except Exception:
        pass
    linked: List[str] = []
    launch_sh = root / "tools/r3_shell_launch.sh"
    for cmd, rel in cmds.items():
        target = root / str(rel)
        if not target.is_file() and not (root / str(rel)).exists():
            continue
        dest = bin_dir / cmd
        if dest.is_symlink() or dest.exists():
            dest.unlink(missing_ok=True)
        dest.symlink_to(target)
        linked.append(cmd)
    for cmd, fid in shell_bins.items():
        dest = bin_dir / cmd
        if dest.is_symlink() or dest.exists():
            dest.unlink(missing_ok=True)
        dest.write_text(
            f"#!/usr/bin/env bash\nexec env AA_PROJECT_ROOT={root} {launch_sh} {fid}\n",
            encoding="utf-8",
        )
        dest.chmod(0o755)
        linked.append(cmd)

    # Legacy-Aliase → R3 (Kompatibilität)
    for old, new in (
        ("active-alpha-preview", "r3-cockpit"),
        ("active-alpha-show", "r3-show"),
        ("alpha-model", "r3-cockpit"),
    ):
        o = bin_dir / old
        n = bin_dir / new
        if new.startswith("tools/"):
            target = root / new
            if target.is_file():
                if o.is_symlink() or o.exists():
                    o.unlink(missing_ok=True)
                o.write_text(
                    f"#!/usr/bin/env bash\nexec env AA_PROJECT_ROOT={root} {target}\n",
                    encoding="utf-8",
                )
                o.chmod(0o755)
                linked.append(old)
            continue
        if n.is_symlink() or n.exists():
            if o.is_symlink() or o.exists():
                o.unlink(missing_ok=True)
            o.symlink_to(n)

    delay = int(cfg.get("autostart_delay_sec") or 28)
    session_sh = root / "tools/r3_session_autostart.sh"
    session_sh.chmod(0o755)

    entries: Dict[str, str] = {}
    autostart_id = "r3-os-session.desktop"
    autostart_name = os_name
    autostart_comment = f"{tagline} · Session"
    autostart_icon = icon_name
    autostart_categories = str(cfg.get("categories") or "System;")
    autostart_keywords = "alpha;model;cockpit;session"
    autostart_wm = runtime_wm
    autostart_exec = f"env AA_PROJECT_ROOT={root} {session_sh}"
    autostart_hidden = False
    autostart_no_display = False
    try:
        from analytics.r3_community_stealth import load_community_stealth, stealth_desktop_meta

        stealth = load_community_stealth(root)
        if stealth.get("enabled"):
            autostart_id = str(stealth.get("autostart_desktop_id") or "xdg-user-session.desktop")
            meta = stealth_desktop_meta(stealth)
            autostart_name = meta["name"]
            autostart_comment = meta["comment"]
            autostart_icon = meta["icon"]
            autostart_categories = meta["categories"]
            autostart_keywords = meta["keywords"]
            autostart_wm = meta["wm_class"]
            autostart_hidden = bool(stealth.get("hidden_from_menus", True))
            autostart_no_display = bool(stealth.get("hidden_from_menus", True))
            if stealth.get("hub_only_default", True):
                autostart_exec = f"env AA_PROJECT_ROOT={root} R3_SESSION_HUB_ONLY=1 {session_sh}"
    except Exception:
        pass

    entries[autostart_id] = _desktop_entry(
        name=autostart_name,
        comment=autostart_comment,
        exec_line=autostart_exec,
        path=root,
        icon=autostart_icon,
        categories=autostart_categories,
        keywords=autostart_keywords,
        autostart=True,
        delay=delay,
        wm_class=autostart_wm,
        hidden_from_menus=autostart_hidden,
        no_display=autostart_no_display,
    )

    entries["Alpha-Model.desktop"] = _desktop_entry(
        name=os_name,
        comment=str(tagline or "Aktienprognosen für Trading212."),
        exec_line=f"env AA_PROJECT_ROOT={root} {root}/tools/r3_cockpit.sh",
        path=root,
        icon=icon_name,
        categories=str(cfg.get("categories") or "System;Finance;"),
        keywords="r3;prognose;trading212",
        wm_class=runtime_wm,
    )

    # Nur R3 auf dem Desktop — Agent, Order-Desk und Shell-Kacheln laufen im Hintergrund / über Hub.
    for extra_id in (
        "Alpha-Model-Agent.desktop",
        "R3-Order-Desk.desktop",
        "R3-Status.desktop",
    ):
        for base in (apps, autostart, root):
            p = Path(base) / extra_id
            if p.is_file():
                p.unlink()
                removed.append(str(p))
    try:
        from analytics.r3_ubuntu_shell import shell_desktop_entries

        for fname in shell_desktop_entries(root, os_name=os_name, icon_name=icon_name):
            for base in (apps, root):
                p = Path(base) / fname
                if p.is_file():
                    p.unlink()
                    removed.append(str(p))
    except Exception:
        pass

    written: List[str] = []
    for fname, body in entries.items():
        if fname == autostart_id:
            p = autostart / fname
        else:
            p = apps / fname
        p.write_text(body, encoding="utf-8")
        p.chmod(0o644)
        written.append(str(p))

    if autostart_id != "r3-os-session.desktop":
        legacy = autostart / "r3-os-session.desktop"
        if legacy.is_file():
            legacy.unlink()
            removed.append(str(legacy))

    # Projekt-Desktop — nur R3-Launcher (kein Agent/Order-Desk auf dem Desktop)
    if "Alpha-Model.desktop" in entries:
        body = entries["Alpha-Model.desktop"]
        (root / "Alpha-Model.desktop").write_text(body, encoding="utf-8")
        (root / "R3-OS.desktop").write_text(body, encoding="utf-8")
    agent_proj = root / "Alpha-Model-Agent.desktop"
    if agent_proj.is_file():
        agent_proj.unlink()
        removed.append(str(agent_proj))

    # Status-Verzeichnis
    share.mkdir(parents=True, exist_ok=True)

    try:
        from analytics.operator_public_status import publish_public_status

        publish_public_status(root, notify=False)
    except Exception:
        pass

    try:
        subprocess.run(["update-desktop-database", str(apps)], check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass

    return {
        "ok": True,
        "os_name": os_name,
        "os_full_de": full,
        "icon": str(icon_dest),
        "share_dir": str(share),
        "written": written,
        "bin_linked": linked,
        "removed_legacy": removed,
        "headline_de": f"{full} — Desktop installiert",
        "message_de": "Menü, Autostart und Befehle sind jetzt R3 — kein Active Alpha auf dem Desktop.",
    }


def _collect_r3_bin_names(root: Path) -> List[str]:
    """Alle von install_desktop_os angelegten Befehlsnamen."""
    root = Path(root).resolve()
    cfg = load_desktop_os(root)
    names: List[str] = list((cfg.get("bin_commands") or {}).keys())
    names.extend(
        [
            "active-alpha-preview",
            "active-alpha-show",
            "r3-preserve",
        ]
    )
    try:
        from analytics.r3_ubuntu_shell import load_ubuntu_shell

        shell_cfg = load_ubuntu_shell(root)
        names.extend(str(k) for k in (shell_cfg.get("quick_bin_commands") or {}).keys())
    except Exception:
        pass
    return sorted(set(str(n) for n in names if n))


def _is_r3_local_bin(name: str) -> bool:
    n = str(name)
    if n in {"r3", "ollama"}:
        return n == "r3"
    prefixes = ("r3-", "alpha-model", "active-alpha")
    return any(n.startswith(p) for p in prefixes)


def purge_r3_local_apps(root: Path) -> Dict[str, Any]:
    """Alle R3-Lokal-Anwendungen deinstallieren — Desktop, Menü, Autostart, ~/.local/bin."""
    root = Path(root).resolve()
    cfg = load_desktop_os(root)
    removed: List[str] = []

    launcher_ids: List[str] = list(cfg.get("desktop_launcher_ids") or ["Alpha-Model.desktop"])
    launcher_ids.extend(
        [
            "R3-OS.desktop",
            "Alpha-Model-Agent.desktop",
            "R3-Order-Desk.desktop",
            "R3-Status.desktop",
            "Active-Alpha-Chat.desktop",
            "Marktanalyse.desktop",
            "r3-os-session.desktop",
        ]
    )
    launcher_ids.extend(str(x) for x in (cfg.get("remove_legacy_desktop_ids") or []))
    try:
        from analytics.r3_ubuntu_shell import shell_desktop_entries

        launcher_ids.extend(shell_desktop_entries(root, os_name="R3", icon_name="r3-os").keys())
    except Exception:
        pass

    desktop_bases = [
        _home() / "Desktop",
        _home() / ".local/share/applications",
        Path(os.environ.get("XDG_CONFIG_HOME", _home() / ".config")) / "autostart",
        root,
    ]
    seen_desktop: set[str] = set()
    for lid in launcher_ids:
        if not lid or lid in seen_desktop:
            continue
        seen_desktop.add(lid)
        for base in desktop_bases:
            p = Path(base) / lid
            if p.is_file():
                p.unlink()
                removed.append(str(p))

    apps_dir = _home() / ".local/share/applications"
    if apps_dir.is_dir():
        for p in apps_dir.iterdir():
            if not p.is_file() or not p.name.endswith(".desktop"):
                continue
            low = p.name.lower()
            if (
                low.startswith("r3")
                or low.startswith("alpha-model")
                or low.startswith("alpha-")
                or low.startswith("active-alpha")
                or low == "marktanalyse.desktop"
            ):
                p.unlink()
                removed.append(str(p))

    bin_dir = _home() / ".local/bin"
    known_bins = set(_collect_r3_bin_names(root))
    if bin_dir.is_dir():
        for p in bin_dir.iterdir():
            if p.name in known_bins or _is_r3_local_bin(p.name):
                p.unlink(missing_ok=True)
                removed.append(str(p))

    apps = _home() / ".local/share/applications"
    try:
        subprocess.run(["update-desktop-database", str(apps)], check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass

    disposition = _load_json(root / "control/r3_pc_app_disposition.json")
    doc: Dict[str, Any] = {
        "ok": True,
        "removed": removed,
        "removed_count": len(removed),
        "headline_de": "R3-Lokal-Anwendungen entfernt",
        "message_de": (
            f"{len(removed)} Einträge gelöscht (Desktop, Menü, Autostart, ~/.local/bin). "
            "Hub weiterhin: python3 tools/preview_hub.py"
        ),
        "functional_technical_executive_de": disposition.get("functional_technical_executive_de") or [],
        "removed_non_functional_de": disposition.get("removed_non_functional_de") or [],
    }
    try:
        from aa_safe_io import atomic_write_json

        atomic_write_json(root / "evidence/r3_local_apps_purge_latest.json", doc)
    except Exception:
        pass
    return doc


def purge_desktop_launchers(root: Path) -> Dict[str, Any]:
    """Legacy-Alias — vollständige Deinstallation."""
    return purge_r3_local_apps(root)


def install_session_autostart(root: Path) -> Dict[str, Any]:
    """Login-Autostart — R3-Session (Hub + Cache); Community-Stealth optional."""
    root = Path(root).resolve()
    cfg = load_desktop_os(root)
    os_name = str(cfg.get("os_name") or "R3")
    tagline = str(cfg.get("tagline_de") or "Exec-Spiegel")
    icon_name = str(cfg.get("icon") or "r3-os")
    delay = int(cfg.get("autostart_delay_sec") or 28)
    autostart = Path(os.environ.get("XDG_CONFIG_HOME", _home() / ".config")) / "autostart"
    autostart.mkdir(parents=True, exist_ok=True)
    session_sh = root / "tools/r3_session_autostart.sh"
    if not session_sh.is_file():
        return {
            "ok": False,
            "error_de": f"Session-Launcher fehlt: {session_sh}",
        }
    session_sh.chmod(0o755)

    stealth_enabled = False
    stealth_doc: Dict[str, Any] = {}
    dest_name = "r3-os-session.desktop"
    exec_prefix = f"env AA_PROJECT_ROOT={root}"
    entry_name = os_name
    entry_comment = f"{tagline} · Hub + Spiegel"
    entry_icon = icon_name
    entry_categories = str(cfg.get("categories") or "System;")
    entry_keywords = "r3;session;hub;cockpit"
    entry_wm = "R3"
    hidden_from_menus = False
    no_display = False

    try:
        from analytics.r3_community_stealth import (
            load_community_stealth,
            purge_legacy_visible_autostart,
            stealth_desktop_meta,
        )

        stealth = load_community_stealth(root)
        if stealth.get("enabled"):
            stealth_enabled = True
            meta = stealth_desktop_meta(stealth)
            dest_name = str(stealth.get("autostart_desktop_id") or "xdg-user-session.desktop")
            entry_name = meta["name"]
            entry_comment = meta["comment"]
            entry_icon = meta["icon"]
            entry_categories = meta["categories"]
            entry_keywords = meta["keywords"]
            entry_wm = meta["wm_class"]
            hidden_from_menus = bool(stealth.get("hidden_from_menus", True))
            no_display = bool(stealth.get("hidden_from_menus", True))
            if stealth.get("hub_only_default", True):
                exec_prefix = f"env AA_PROJECT_ROOT={root} R3_SESSION_HUB_ONLY=1"
            purge_legacy_visible_autostart(root)
    except Exception:
        pass

    body = _desktop_entry(
        name=entry_name,
        comment=entry_comment,
        exec_line=f"{exec_prefix} {session_sh}",
        path=root,
        icon=entry_icon,
        categories=entry_categories,
        keywords=entry_keywords,
        autostart=True,
        delay=delay,
        wm_class=entry_wm,
        hidden_from_menus=hidden_from_menus,
        no_display=no_display,
    )
    dest = autostart / dest_name
    dest.write_text(body, encoding="utf-8")
    dest.chmod(0o644)
    try:
        from analytics.r3_desktop_icon import ensure_home_file_owned

        ensure_home_file_owned(dest)
    except Exception:
        pass

    if stealth_enabled:
        try:
            from analytics.r3_community_stealth import install_systemd_user_session

            stealth_doc = install_systemd_user_session(root)
        except Exception as exc:
            stealth_doc = {"ok": False, "error_de": str(exc)[:120]}

    return {
        "ok": True,
        "autostart_entry": str(dest),
        "delay_sec": delay,
        "community_stealth": stealth_enabled,
        "systemd": stealth_doc,
        "message_de": (
            f"Stealth-Autostart in {delay}s — Hub-only, Hidden ({dest_name})"
            if stealth_enabled
            else f"Login-Autostart in {delay}s — Hub (systemd) + R3-Fenster"
        ),
    }


def install_r3_exec_mirror_app(root: Path, *, session_autostart: bool = True) -> Dict[str, Any]:
    """Eine lokale R3-App — Spiegel der technischen Exekutive (kein Desktop-OS-Paket)."""
    root = Path(root).resolve()
    cfg = load_desktop_os(root)
    os_name = str(cfg.get("os_name") or "R3")
    icon_name = str(cfg.get("icon") or "r3-os")
    apps = _home() / ".local/share/applications"
    bin_dir = _home() / ".local/bin"
    icons = _home() / ".local/share/icons/hicolor/scalable/apps"
    apps.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)

    try:
        from analytics.r3_desktop_icon import install_r3_desktop_icons

        install_r3_desktop_icons(root, icon_name=icon_name)
    except Exception:
        icon_src = root / _ICON_REL
        icon_dest = icons / f"{icon_name}.svg"
        if icon_src.is_file():
            shutil.copy2(icon_src, icon_dest)

    launch = root / "tools/r3_cockpit.sh"
    if not launch.is_file():
        return {
            "ok": False,
            "error_de": f"Launcher fehlt: {launch}",
            "headline_de": "R3 — Installation fehlgeschlagen",
        }
    body = _desktop_entry(
        name=os_name,
        comment="Lokales Fenster (Qt) — Ergebnisse und Auftrag, kein Browser",
        exec_line=(
            f"env AA_PROJECT_ROOT={root} R3_SESSION=1 R3_NATIVE_SHELL=1 {launch}"
        ),
        path=root,
        icon=icon_name,
        categories="System;Finance;",
        keywords="r3;exekutive;trading212",
        wm_class="R3",
    )
    app_path = apps / "R3.desktop"
    app_path.write_text(body, encoding="utf-8")
    app_path.chmod(0o644)
    try:
        from analytics.r3_desktop_icon import ensure_home_file_owned

        ensure_home_file_owned(app_path)
    except Exception:
        pass

    try:
        from analytics.r3_home_ownership import fix_r3_home_ownership

        fix_r3_home_ownership(root)
    except Exception:
        pass

    bin_path = bin_dir / "r3"
    if bin_path.is_symlink() or bin_path.exists():
        bin_path.unlink(missing_ok=True)
    bin_path.symlink_to(launch)

    try:
        subprocess.run(["update-desktop-database", str(apps)], check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass

    autostart_doc: Dict[str, Any] = {}
    if session_autostart:
        try:
            autostart_doc = install_session_autostart(root)
        except OSError as exc:
            autostart_doc = {"ok": False, "error_de": str(exc)[:120]}

    return {
        "ok": True,
        "app_id": "r3_exec_mirror",
        "hub_path": "/r3",
        "desktop_entry": str(app_path),
        "bin_command": str(bin_path),
        "session_autostart": autostart_doc,
        "headline_de": f"{os_name} — lokaler Spiegel installiert",
        "message_de": (
            "Ergebnisse + Auftrag. Login-Autostart aktiv (Hub systemd + R3-Fenster)."
            if autostart_doc.get("ok")
            else "Ergebnisse + Auftrag. Autostart: bash tools/install_r3_app.sh"
        ),
    }
