# Lokales Git (ohne GitHub)

Dieses Projekt wird **nur lokal** mit Git versioniert. Es ist **kein** `origin`/GitHub
vorgesehen — kein `git push`, keine Pull Requests.

## Hauptbranch

| Branch | Rolle |
|--------|--------|
| **`development/p10-p12-integration-spine`** | Integrations- und Produktionsstand (Live-Trading, EXE, Dashboard) |
| **`main`** | Zeiger auf denselben Stand wie der Spine (für einfache Orientierung) |

Historische Zweige (`codex/*`, `remediation/*`) bleiben als **Labels** erhalten, zeigen nach
`tools/sync_local_git_branches.ps1` auf den aktuellen Integrations-Commit.

## Tägliche Arbeit

```bat
cd /d e:\active_alpha_model
git status
git add -A
git commit -m "kurze Beschreibung"
```

Optional alle lokalen Branch-Zeiger aktualisieren:

```powershell
powershell -File tools\sync_local_git_branches.ps1
```

## Merge-Status

Alle früheren Entwicklungszweige sind **bereits in der Spine-Historie enthalten**
(lineare Merge-Kette bis G0R4R2). Es gibt keine offenen lokalen Branches mit
Commits, die noch nicht im Spine sind.

Neue Arbeit immer auf **`development/p10-p12-integration-spine`** (oder `main`).

## Nicht committen

- `Marktanalyse.exe` (Binary — nur `Marktanalyse.exe.sha256`)
- `trading212_zugangsdaten.env`, `.env`
- `.marktanalyse_app.lock`

## EXE bauen

```bat
.venv\Scripts\python.exe tools\build_v5r_standalone_exe.py
```

Doppelklick auf `Marktanalyse.exe` im Projektroot (mit `.venv` für Signal).
