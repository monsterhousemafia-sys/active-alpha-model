"""Hilfsfunktion — Tresor automatisch öffnen und Antwort anreichern."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from analytics.secret_redaction import safe_public_doc


def enrich_with_vault_portal(
    doc: Dict[str, Any],
    root: Path,
    *,
    context: str,
    force_manage: bool = False,
    always_try: bool = False,
) -> Dict[str, Any]:
    """Öffnet Schlüssel-Tresor bei Bedarf und hängt vault_portal an doc."""
    from analytics.secure_credential_portal import auto_open_if_needed, credential_action_needed

    root = Path(root)
    need = credential_action_needed(root, force_manage=force_manage)
    if not always_try and not need.get("needed"):
        return doc
    portal = auto_open_if_needed(root, context=context, force_manage=force_manage)
    if portal:
        out = dict(doc)
        out["vault_portal"] = safe_public_doc(portal)
        out["vault_auto_opened"] = bool(portal.get("portal_opened"))
        if portal.get("message_de"):
            out["vault_message_de"] = portal.get("message_de")
        return out
    return doc
