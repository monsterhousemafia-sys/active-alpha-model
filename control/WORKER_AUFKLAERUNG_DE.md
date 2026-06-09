# Active Alpha — Kollektive Rechenrevolution

**Worker** = jeder, der **Rechenleistung** bereitstellen kann — Windows, Mac oder Linux mit Python 3. Kein Broker, kein Geld, kein Spezialwissen.

## Wofür stellst du dich bereit?

Du leihst **Rechenleistung** deines PCs für ein gemeinsames Aktien-Research-System — nicht dein Geld, nicht dein Broker-Konto, nicht deine Passwörter.

| Du gibst | Du gibst **nicht** |
|----------|-------------------|
| CPU-Kerne (Hintergrund, niedrige Priorität) | Trading212 / Broker-Zugang |
| RAM für Python-Checks | Order-Freigaben oder echtes Geld |
| Netzwerk zum König-PC im LAN | Deine privaten Aktienpositionen (außer du betreibst selbst einen vollen Pilot) |
| Einen Ordner auf deiner Festplatte | Admin-Rechte auf fremden Rechnern |

## Was passiert technisch?

1. Du erhältst einen **Worker-Ordner** vom König (Export).
2. Beim Start meldet dein PC: **wie viele Kerne**, wie viel RAM frei, ob Preview-Checks lokal grün sind.
3. Alles erscheint **zentral** im Command Center unter „Zentrale Rechenleistung“.
4. Der König koordiniert Research, Backtests und Preview — dein PC ist **Kraftwerk**, nicht Steuerzentrale.

## Kollektive Aktienrevolution — was das bedeutet

- **Transparent:** Jeder sieht im Hub, wie viele Köpfe und Kerne mitdenken.
- **Dezentral in der Breite, zentral in der Strategie:** Viele Rechner, ein Cockpit.
- **Kein Hedge-Fund-Geheimnis:** Open Research, gemeinsame Evidenz, gemeinsamer Lernkreis.
- **Deine Rolle:** Du machst das System **schneller und robuster** — mehr Backtests, mehr Varianten, weniger Wartezeit.

## Was du tun musst

```bash
cd <empfangener-ordner>
./ACTIVE_ALPHA_WORKER_START.sh
```

Oder: PC neu anmelden (Autostart verbindet automatisch).

## Was du jederzeit tun kannst

```bash
systemctl --user stop active-alpha-preview-worker.service
systemctl --user disable active-alpha-preview-worker.service
```

Ordner löschen = vollständig raus aus der Kollektiv-Leistung.

## Grenzen (ehrlich)

- Ein Klick im Browser allein reicht nicht — der Worker muss einmal laufen.
- Ohne erreichbaren König-Hub (`http://<könig-lan-ip>:17890`) keine Meldung.
- Test vom Worker: `curl -fsS http://<könig-ip>:17890/api/health`
- König-Firewall: ggf. `sudo ufw allow 17890/tcp`
- Schwacher Laptop hilft weniger als ein Desktop mit vielen Kernen — jeder Beitrag zählt trotzdem.

## Fragen?

Command Center des Königs im Browser öffnen — dort siehst du alle Knoten live.
