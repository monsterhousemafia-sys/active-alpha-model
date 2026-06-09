# Remote-Worker — stabil über Internet

Worker können **überall** mitmachen. URL und ZIP bleiben **stabil** — kein Neuversand nach Neustart.

## Einmalig einrichten (König)

### Server starten (ein Befehl)

```bash
ai_kernel server-bootstrap
# oder: bash tools/bootstrap_stable_server.sh
```

Startet **einen** Hub, Tunnel, systemd-Autostart.

### Stabile URL nach Neustart (Pflicht für Dauerbetrieb)

```bash
# Option A: interaktiv
bash tools/setup_cloudflare_tunnel_token.sh

# Option B: ohne Dialog (Token + URL in Datei)
cp control/server.env.example control/server.env
# Werte eintragen, dann:
bash tools/bootstrap_stable_server.sh
```

Einmalig Cloudflare Zero Trust: Tunnel anlegen → Public Hostname `http://127.0.0.1:17890` → Token + HTTPS-URL eintragen.

Danach:
- URL bleibt **gleich** nach PC-Neustart
- `join_token` bleibt **gleich** — ZIP muss nicht neu verschickt werden
- systemd startet Hub + Tunnel automatisch

### Schnellstart (ohne Token)

```bash
ai_kernel spread-remote
```

Funktioniert sofort, aber Quick-Tunnel-URL kann nach Neustart wechseln → danach Token-Setup.

## ZIP verschicken

```bash
ai_kernel spread-remote    # nur wenn Tunnel/Export nötig
# oder: ~/active_alpha_worker_LITE.zip
```

`spread-secure` **ändert Token/URL nicht** und exportiert nur, wenn sich etwas geändert hat.

## Worker (ein Schritt)

| System | Aktion |
|--------|--------|
| Windows | `Windows_START.bat` |
| macOS | `Mac_START.command` |
| Linux | `Linux_START.sh` |

Nur **Python 3** — kein VPN auf Worker-Seite (bei Cloudflare-Tunnel).

## Status

```bash
ai_kernel spread-remote-status
ai_kernel spread-plan
```

## Autostart (systemd user)

```bash
bash tools/install_remote_systemd.sh
```

## Alternative: Tailscale

```bash
ai_kernel spread-remote --remote-mode tailscale
```

König **und** Worker brauchen Tailscale — dafür private Verbindung.
