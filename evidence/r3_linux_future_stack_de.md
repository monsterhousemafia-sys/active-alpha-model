# Linux-Unterbau 2026 — Zukunft & R3 System Plane

**Stand:** 2026-06-06 · R3 abstrahiert die Schicht — du bedienst Slider und Buttons, nicht nmcli/pactl/loginctl.

## Kurzfassung

| Schicht | Ubuntu heute | Zukunft (2025–2027) | R3 heute |
|---------|--------------|---------------------|----------|
| **Kernel** | C, Syscalls | Rust permanent · io_uring+eBPF | `plane.stack` — Kernel-Info, keine CLI |
| **Netzwerk** | NetworkManager, nmcli | D-Bus/libnm bleibt; sync API deprecated | Strukturiertes WLAN-Panel, Ein/Aus per Klick |
| **Audio** | PipeWire (Ubuntu 24+) | wpctl/WirePlumber; pactl nur Kompat | Slider + Stumm; wpctl bevorzugt |
| **Session** | systemd-logind, loginctl | Migration D-Bus → **Varlink** | Sperren/Abmelden via loginctl zuerst |

---

## Linux-Kernel

- **Rust** ist seit Kernel Maintainer Summit 2025 **dauerhaft** im Kernel (nicht mehr experimentell).
- **io_uring + eBPF**: BPF-gesteuerte Event-Loops, feingranulare SQE-Filter — schnellere, sicherere I/O.
- **R3**: Kein Kernel-Hacking in Schritt A. Die System Plane zeigt Kernel-Version und merkt die Zukunftsschicht an; Steuerung läuft über Hub-API.

Quellen: [Rust im Kernel (DevClass 2025)](https://www.devclass.com/development/2025/12/15/rust-boosted-by-permanent-adoption-for-linux-kernel-code/1725322), [BPF + io_uring (LWN 2026)](https://lwn.net/Articles/1062286/)

---

## nmcli / NetworkManager

- **Kein Ersatz** für NetworkManager — die **D-Bus-API** bleibt die stabile Schnittstelle.
- **nmcli** ist ein Client; libnm empfiehlt **asynchrone** D-Bus-Aufrufe (synchrone API deprecated).
- **R3 System Plane**: parst nmcli in JSON (SSID, Signal, Geräte), WLAN-Radio per Button — kein Terminal.

Quellen: [NetworkManager Developers](https://networkmanager.dev/docs/developers/), [libnm Usage](https://www.networkmanager.dev/docs/libnm/latest/usage.html)

---

## pactl / PipeWire / wpctl

- **PipeWire + WirePlumber** ist Standard auf modernem Ubuntu/Debian.
- **pactl** spricht oft mit `PulseAudio (on PipeWire …)` — reine Kompatibilitätsschicht.
- **Zukunft**: natives **wpctl** (Volume, Default, Status) statt rohem pactl.
- **R3**: erkennt Backend automatisch, bevorzugt `wpctl set-volume`, Fallback `pactl`.

Quellen: [PipeWire README](https://github.com/PipeWire/pipewire/blob/master/README.md), [wpctl(1)](https://pipewire.pages.freedesktop.org/wireplumber/tools/wpctl.html)

---

## loginctl / systemd-logind

- **Migration zu Varlink** läuft (Issue #41560, Phase 1 merged 2026): schnellere Roundtrips, weniger D-Bus-Overhead.
- **loginctl** wird Client für Varlink + D-Bus-Fallback.
- **R3**: `loginctl lock-session` / `terminate-user` **vor** gnome-session-quit — GNOME nur Fallback.

Quellen: [systemd logind Varlink Migration](https://github.com/systemd/systemd/issues/41560), [loginctl manual](https://freedesktop.org/software/systemd/man/latest/loginctl.html)

---

## Bedienung — besser als „altes Linux“

| Alt (CLI) | R3 System Plane |
|-----------|-----------------|
| `nmcli dev wifi` | Netzwerk-Panel: Netze, Signal, WLAN an/aus |
| `pactl set-sink-volume …` | Slider 0–100 %, Stumm-Toggle |
| `loginctl lock-session` | Kachel Sperren + Power-Menü |
| Scroll im Terminal-Output | Scroll im Panel + Mausrad auf Slider |

API: `GET /api/desktop/plane` · `POST /api/desktop/plane` mit `{"action":"volume","pct":75}`

Konfiguration: `control/r3_system_plane.json` · Code: `analytics/r3_system_plane.py`
