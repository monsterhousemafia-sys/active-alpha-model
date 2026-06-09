"""Trading 212 auth profile types — monitoring vs confirmed execution."""
from __future__ import annotations

PROFILE_MONITORING_READONLY = "T212_PROFILE_MONITORING_READONLY"
PROFILE_CONFIRMED_EXECUTION = "T212_PROFILE_CONFIRMED_EXECUTION"

PROFILE_LABELS = {
    PROFILE_MONITORING_READONLY: "Read-Only Monitoring",
    PROFILE_CONFIRMED_EXECUTION: "Confirmed Execution (Echtgeld nach Bestätigung)",
}
