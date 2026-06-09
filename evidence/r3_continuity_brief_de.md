# R3 Kontinuität — Cursor-Anker

Wir bauen R3 als Betriebssystem-Oberfläche auf Ubuntu.

**Anker:** Cursor-Agent (dieser Chat) — vollständig erhalten bis zum Ende.
**R3 Desktop:** Cockpit :17890/desktop — System-Oberfläche.
**Ollama:** Nur Fallback im Cockpit — ersetzt den Anker nicht.

## Feste Pfade
- Arbeitsbaum: /home/machinax7/active_alpha_model
- Anker-Archiv: ~/.local/share/r3-os/conversation/
- Cockpit: http://127.0.0.1:17890/desktop
- Tunnel-KI: evidence/ki_tunnel_connection_latest.json

## Erreicht (Auszug)
- Phase B aktiv (~40%): Native Apps, Pakete; offen: Login/Session, WM/Spaces, H1-Seal
- Desktop-Migration: Cursor primär, R3 Vollbild, Ollama Fallback
- KI-Tunnel: Cloudflare Quick-Tunnel aktiv
- Schritt A Code 100% · H1 parallel ~99% RUNNING stabil

## Als Nächstes
- Meilenstein 1: Login + Session-Manager
- Fenster-Management (Snap/Spaces)
- H1-Seal abwarten (automatisch)
- Anker sichern: python3 tools/ai_kernel.py r3-preserve

## Befehle (Anker + System)
- Hier in Cursor schreiben — Hauptkanal
- python3 tools/ai_kernel.py r3-preserve
- python3 tools/ai_kernel.py r3-desktop-update
- Cockpit-Slash: /status · /geheimnis · /desktop

## Letzte Gesprächspunkte


Aktualisiert: 2026-06-08T14:01:54+00:00
Quelle Arbeitsbaum: /home/machinax7/active_alpha_model
