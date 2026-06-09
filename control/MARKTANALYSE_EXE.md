# Zentrale Marktanalyse.exe

| Was | Pfad |
|-----|------|
| **Einzige Produkt-EXE** | `Marktanalyse.exe` (Projektroot) |
| **Integritäts-Hash** | `Marktanalyse.exe.sha256` |
| **Start** | `run_live_trading_start.bat` (Python) oder `run_live_trading_start.bat --exe` |

Nicht mehr nutzen als Laufzeit:

- `dist/Marktanalyse.exe` (wird nach Build entfernt)
- `Marktanalyse/Marktanalyse.exe` (alter onedir-Launcher)
- `tools/decision_cockpit_readonly_launcher.py` für Endnutzer (nur Entwicklung/CI)

Build: `.venv\Scripts\python.exe tools\build_v5r_standalone_exe.py`
