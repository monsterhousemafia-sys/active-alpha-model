"""Lokaler Parallel-Compute — 3× Ollama-Worker + Synthese (keyless deep/plan)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _local_chat(
    root: Path,
    messages: List[Dict[str, str]],
    *,
    model: str,
    role: str,
    timeout_s: float = 180.0,
) -> str:
    from analytics.local_llm_bridge import chat_completion

    tip, _ = chat_completion(root, messages, model=model, role=role, timeout_s=timeout_s)
    return str(tip or "").strip()


def fetch_local_parallel_tip(
    root: Path,
    question: str,
    *,
    sys_prompt: str,
    context: str,
    tier: Dict[str, Any],
    pick: Dict[str, Any],
    mode: str = "kombi",
) -> Tuple[str, Dict[str, Any]]:
    """3 parallele Ollama-Worker + Synthese — Spiegel zu Gemini compute_boost."""
    root = Path(root)
    workers = 3
    worker_model = str(pick.get("model") or "")
    role = "kombi_synthesis" if mode == "kombi" else "chat"
    sub_tasks = [
        f"Risiken und Blocker analysieren: {question}",
        f"Konkrete nächste king_ops-Schritte: {question}",
        f"Evidence-Implikationen für Active Alpha: {question}",
    ][:workers]
    results: List[str] = []

    def _worker(sub_q: str) -> str:
        user = f"{sub_q}\n\n{context}" if context else sub_q
        return _local_chat(
            root,
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
            model=worker_model,
            role=role,
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_worker, sq) for sq in sub_tasks]
        for fut in as_completed(futures):
            try:
                results.append(str(fut.result() or "").strip())
            except Exception as exc:
                results.append(f"(Worker-Fehler: {exc})")

    synth_user = (
        f"Nutzerfrage: {question}\n\n"
        f"Parallele Worker ({len(results)}):\n"
        + "\n---\n".join(f"W{i + 1}:\n{r}" for i, r in enumerate(results))
        + (f"\n\n{context}" if context else "")
    )
    tip = _local_chat(
        root,
        [
            {
                "role": "system",
                "content": sys_prompt + " Synthetisiere die Worker-Ergebnisse präzise auf Deutsch.",
            },
            {"role": "user", "content": synth_user},
        ],
        model=worker_model,
        role=role,
        timeout_s=240.0,
    )
    meta = {
        "model": worker_model,
        "parallel_workers": workers,
        "compute_boost": True,
        "provider": "ollama_parallel",
    }
    return tip, meta
