# Active Alpha — Open Research auf Linux

**Ziel in einem Satz:** Eine offene, Linux-native Research-Plattform für systematisches Aktien-Research — viele Rechner liefern Rechenleistung, ein transparentes Command Center bündelt Evidenz und Evolution.

## Was ist das?

- **Preview Command Center** — täglicher System-Check im Browser (Ampel, Kreis-Score, Cockpit)
- **Preview Federation** — beliebiger PC (Windows, macOS, Linux) spendet CPU per Doppelklick
- **Kein Cloud-Zwang**, kein Broker-Zugang für Worker
- **Orders nur mit GUI-Bestätigung** — kein autonomes Echtgeld

## Mitmachen (Worker) — kinderleicht, auch über Internet

### König exportiert (einmal)

```bash
cd ~/active_alpha_model && ai_kernel spread-remote
```

Das richtet **Cloudflare-Tunnel** (oder Tailscale) ein, setzt Token und baut `~/active_alpha_worker_LITE.zip`.  
Per **WhatsApp, E-Mail, USB** verschicken — Worker muss **nicht** im gleichen WLAN sein.

Details: [REMOTE_WORKER_DE.md](REMOTE_WORKER_DE.md)

Nur LAN (gleiches WLAN):

```bash
ai_kernel preview-export-lite
```

### Worker startet (ein Schritt)

| System | Aktion |
|--------|--------|
| **Windows** | ZIP entpacken → Doppelklick `Windows_START.bat` |
| **macOS** | ZIP entpacken → Doppelklick `Mac_START.command` |
| **Linux** | ZIP entpacken → `./Linux_START.sh` |

Voraussetzung: **Python 3** (von [python.org](https://www.python.org/downloads/) — unter Windows „Add to PATH“ ankreuzen).

**Erreichbarkeit testen (vom Worker):**
```bash
curl -fsS http://<könig-ip>:17890/api/health
```

**Firewall König (falls aktiv):**
```bash
sudo ufw allow 17890/tcp
```

## Linux Voll-Bundle (optional, Power-User)

```bash
ai_kernel preview-export
# → großer Ordner (~1,3 GB), nur Linux:
cd <empfangener-ordner> && ./ACTIVE_ALPHA_WORKER_START.sh
```

## Stack

Python · systemd user timers · HTTP-Hub (LAN `:17890`) · optional NVMe · Ollama lokal gedrosselt

## Grenzen

Pilot, kein Hedge-Fund-Produkt. Worker spenden **Rechenleistung** — ersetzen keinen vollen Live-Pilot auf dem König-PC.

## Links im Projekt

- Mission (Pflichtlektüre im Hub): `control/PREVIEW_MANIFEST_DE.json`
- Worker-Aufklärung: `control/WORKER_AUFKLAERUNG_DE.md`
- Zeitplan Verbreitung: `control/COMMUNITY_SPREAD_PLAN.json`
- Status: `ai_kernel spread-plan`
- Ausbreitung sichern (Tunnel + ZIP + Forum): `bash tools/king_ops.sh community-spread --repair`
- Glasfaser-Umzug (offline-sicher): `bash tools/king_ops.sh glasfaser --init` → Plan `control/GLASFASER_OFFLINE_PLAN.json`
- Forum-Entwurf: `evidence/community_spread_forum_de.txt`
