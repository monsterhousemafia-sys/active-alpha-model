"""Load .env and migrate Trading 212 credentials to persistent local storage at startup."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from integrations.trading212.t212_credentials_ui_controller import (
    ensure_session_from_persisted_credentials,
    maybe_migrate_env_credentials_to_disk,
)
from integrations.trading212.t212_env_file_loader import load_trading212_env_file


def bootstrap_trading212_credentials(root: Path) -> Dict[str, Any]:
    """Load ``root/.env``, migrate env to DPAPI, restore session from disk."""
    load_trading212_env_file(Path(root))
    migrated = maybe_migrate_env_credentials_to_disk(Path(root))
    restored = ensure_session_from_persisted_credentials(Path(root))
    from integrations.trading212.t212_execution_profile_bootstrap import ensure_execution_profile_ready

    exec_restore = ensure_execution_profile_ready(Path(root))
    return {"migration": migrated, "session_restore": restored, "execution_restore": exec_restore}
