# Marktanalyse — Linux

Gleiches Muster wie Windows: ein Start-Skript, ein Setup, ein Python-Einstieg.

| Windows | Linux |
|---------|-------|
| `setup_active_alpha_env.bat` | `bash tools/setup_linux_native.sh` |
| `run_pilot_start.bat` | `bash run_marktanalyse_bash.sh` (Bash) · `bash run_marktanalyse_linux.sh` (GUI) |
| `aa_pilot_launch.py` | `aa_pilot_launch.py` |

```bash
sudo apt install python3.14-venv python3-pip libxcb-cursor0   # einmalig
bash tools/setup_linux_native.sh
python3 tools/ai_kernel.py ready
bash run_marktanalyse_bash.sh start
bash run_marktanalyse_bash.sh menu
bash tools/king_ops.sh marktanalyse status
bash run_marktanalyse_linux.sh --dev
```

Bash-Cockpit (`tools/marktanalyse_bash.sh`): Preflight, Status, Picks, Gates, Predict — ohne DISPLAY, fail-closed.

Linux-Host-Logik: `execution/linux_security_boundary.py`  
Agent-Regeln: `control/AI_KERNEL.json`, `.cursor/rules/ai-kernel.mdc`
