# Ubuntu → R3 Feature-Matrix

**Stand:** 2026-06-06 · Live im Cockpit unter `#r3-ubuntu-closure`

Jede Funktion, die Ubuntu/GNOME dem Nutzer liefert, ist hier **einmal** erfasst und einem R3-Status zugeordnet.

## Legende

| Status | Bedeutung |
|--------|-----------|
| **native** | R3-Cockpit — kein GNOME-Fenster |
| **partiell** | R3 System Plane + Linux-Daemon (NetworkManager, PipeWire, logind) |
| **Schritt B** | Nach H1-Seal: Login, WM, Paketschicht |

## 13 Shell-Kacheln → R3

| Kachel | Ubuntu | R3 heute |
|--------|--------|----------|
| Aktien | — | native (DAILY_ALPHA_H1) |
| Dateien | Nautilus | native Browser + Text-Vorschau |
| Terminal | gnome-terminal | native Befehlszeile (Whitelist) |
| Rechner | gnome-calculator | native JS-Rechner |
| Screenshot | gnome-screenshot | R3-UI · Backend scrot/gcc |
| Einstellungen | GCC | native R3-Panel + Unterpanels |
| Programme | GNOME Overview | native .desktop-Liste |
| Sperren | loginctl | native → loginctl |
| Netzwerk | GCC WiFi | native System Plane (WLAN-Buttons) |
| Bluetooth | GCC BT | native Panel |
| Ton | GCC Sound | native Slider (wpctl/pactl) |
| Bildschirm | GCC Display | native xrandr-Info |
| Energie | GCC Power | native upower/acpi |

## Fusion (zusätzlich)

Spotlight · Dock · Control Center · Power-Menü · Update-Badge · Mitteilungen — **native** im Cockpit.

## Schritt B (nach H1)

Login · Session-Manager · Fenster/Snap · R3-Paket-Install · vmlinuz nur mit Governance.

## Prüfung

```bash
python3 tools/ai_kernel.py r3-migration-check   # R3 Chat
curl -s http://127.0.0.1:17890/api/desktop/closure | python3 -m json.tool
```

Konfiguration: `control/r3_ubuntu_closure.json` · Code: `analytics/r3_ubuntu_closure.py`
