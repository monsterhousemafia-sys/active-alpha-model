#!/usr/bin/env python3
"""Active Alpha Stufe 3 — lokaler Chat (Ollama), Cursor-Ersatz für Betrieb & Fragen."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SLASH = {
    "/kontinuität": "r3-preserve",
    "/kontinuitaet": "r3-preserve",
    "/interface": "human-interface",
    "/ressourcen": "chamber-resources",
    "/handoff": "entfaltung-handoff",
    "/migration": "r3-migration-check",
    "/desktop": "r3-desktop-update",
    "/status": "status",
    "/warnings": "warnings",
    "/warnungen": "warnings",
    "/learn": "learn",
    "/lernen": "learn",
    "/evolve": "evolve",
    "/visibility": "visibility",
    "/h1": "h1-status",
    "/ready": "ready",
    "/maintain": "maintain",
    "/wartung": "maintain",
    "/montag": "trading-day",
    "/circle": "circle",
    "/kreis": "circle",
    "/scope": "scope",
    "/audit": "audit",
    "/refresh": "refresh",
    "/trading-day": "trading-day",
    "/llm": "llm-health",
    "/preview": "gui-preview",
    "/gui-preview": "gui-preview",
    "/wallstreet": "wallstreet",
    "/h1-watch": "h1-watch",
    "/h1-benchmark": "h1-benchmark",
    "/h1-connect": "h1-connect",
    "/h1-distribute": "h1-distribute",
    "/h1-workers": "h1-workers",
    "/worker-status": "h1-workers",
    "/welt-verteilen": "world-spread",
    "/world-spread": "world-spread",
    "/spread-intensiv": "spread-intensify",
    "/spread-intensify": "spread-intensify",
    "/könig-verteilen": "king-distribute",
    "/bash-verteilen": "king-distribute",
    "/king-distribute": "king-distribute",
    "/king-ops": "king-ops",
    "/king-status": "king-status",
    "/king-maintain": "king-maintain",
    "/king-h1-seal": "king-h1-seal",
    "/pipeline": "king-ops pipeline",
    "/tune": "king-ops tune",
    "/king-tune": "king-ops tune",
    "/verify": "king-ops verify",
    "/clean": "king-ops clean",
    "/verteilen": "h1-distribute",
    "/verbinden": "h1-connect",
    "/könig-puls": "king-pulse",
    "/koenig-puls": "king-pulse",
    "/h1-finish": "h1-finish",
    "/launch": "launch-status",
    "/runtime": "runtime-status",
    "/agent-home": "agent-home",
    "/build": "r3-build",
    "/kernel-build": "build-kernel",
    "/monday": "monday-prep",
}


def _help_de(*, chamber: bool = False) -> str:
    base = """
Alpha Model Chat (Stufe 3) — lokales Modell, kein Cursor nötig.

Slash-Befehle (führen ai_kernel aus):
  /status /warnings /learn /evolve /visibility /circle /preview /h1 /ready /maintain /montag /hilfe /quit
"""
    if chamber:
        try:
            from analytics.alpha_model_coding_bridge import render_coding_help_de

            return base + "\n" + render_coding_help_de() + "\n"
        except Exception:
            return (
                base
                + "\nEntfaltungsraum (König-Modus): /diene · /könig · /cursor · /bau · /kombi · /learn · /hilfe\n"
                + "Agent-Dienst (Standard): läuft immer · /quit = neue Session · /dienst-stop = Stopp\n"
                + "Ideal-32B: Chat 14B · /bau Coder-32B (128 Schritte, GPU preload).\n"
                + "Berater: /kombi <frage> (Cloud+Ollama) · /tipp <frage> (nur Cloud)\n"
                + "Internet: /internet · /fetch · /web — Freitext-Fragen zu Netz werden direkt beantwortet.\n"
                + "Freitext: Chat-Agent (128 Schritte) · Code: /bau oder Auto-Routing.\n"
                + "Du bist der König — keine künstlichen Deckel.\n"
            )
    return base + "\nFreitext: Fragen zu Alpha Model, Montag, Evolution, H1 — Auto antwortet mit Kontext.\n"


def _reset_session(messages: list, root: Path) -> None:
    from analytics.local_llm_bridge import initial_messages

    messages.clear()
    messages.extend(initial_messages(root))


def run_repl(
    root: Path,
    *,
    model: str | None = None,
    once: str | None = None,
    serve_mode: bool = False,
) -> int:
    """
    Return codes: 0=beendet · 1=Session neu (Serve) · 2=Ollama fehlt · 3=Dienst-Stopp
    """
    from analytics.local_llm_bridge import chat_completion, health_report, initial_messages, run_kernel_command

    chamber = __import__("os").environ.get("AA_AGENT_CHAMBER", "").strip() in ("1", "true", "yes")
    if chamber:
        try:
            from analytics.alpha_model_king_control import ensure_king_control, format_king_gate_de, force_king_env

            force_king_env()
            try:
                from analytics.ai_kernel_hardware_bond import bond_kernel_to_king_32b

                tier_cfg = {}
                try:
                    from analytics.alpha_model_entfaltung_32b import load_tier_config

                    tier_cfg = load_tier_config(root).get("chat_agent") or {}
                except Exception:
                    pass
                bond_kernel_to_king_32b(
                    root,
                    persist=True,
                    preload=bool(tier_cfg.get("preload_on_start", True)),
                )
            except Exception as exc:
                print(f"[Hardware-Bond] {exc}", file=sys.stderr)
            king = ensure_king_control(root, repair=True)
            if not king.get("ready"):
                print(format_king_gate_de(root), file=sys.stderr)
                return 2
        except Exception as exc:
            print(f"[König-Kontrolle FEHLER] {exc}", file=sys.stderr)
            return 2

    health = health_report(root)
    if not health.get("ready"):
        print(json.dumps(health, indent=2, ensure_ascii=False), file=sys.stderr)
        print(
            "\n[FEHLER] Ollama nicht bereit — bash tools/setup_local_llm.sh\n",
            file=sys.stderr,
        )
        return 2

    messages = initial_messages(root)
    chamber = __import__("os").environ.get("AA_AGENT_CHAMBER", "").strip() in ("1", "true", "yes")
    serve_mode = serve_mode or __import__("os").environ.get("AA_AGENT_SERVE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if chamber:
        try:
            from analytics.alpha_model_agent_home import ensure_agent_home, load_agent_home_config

            ensure_agent_home(root)
            try:
                from analytics.alpha_model_entfaltung_32b import render_chamber_banner

                print(render_chamber_banner(root))
                try:
                    from analytics.king_sovereignty import format_pulse_banner_de

                    print(format_pulse_banner_de(root) + "\n")
                except Exception:
                    pass
                if serve_mode:
                    print(
                        "(Agent-Dienst aktiv — immer für dich da · /quit = neue Session · "
                        "/dienst-stop = Dienst beenden)\n"
                    )
                else:
                    print("(Freie Entfaltung — Session bleibt offen · /quit beendet)\n")
            except Exception:
                label = load_agent_home_config(root).get("label_de") or "Entfaltungsraum"
                print(
                    f"{label} · nur lokal · Ollama 127.0.0.1 · "
                    f"Modell: {health.get('resolved_model')} · /hilfe · /quit"
                )
        except Exception:
            print(
                f"Alpha Model Entfaltungsraum · nur lokal · Ollama 127.0.0.1 · "
                f"Modell: {health.get('resolved_model')} · /hilfe · /quit"
            )
    else:
        print(f"Alpha Model Chat · Modell: {health.get('resolved_model')} · /hilfe · /quit")

    def handle_line(line: str) -> bool:
        text = line.strip()
        if not text:
            return True
        low = text.lower()
        if low in ("/quit", "/ende", "/exit", "quit", "exit"):
            if serve_mode:
                print("\n[Neue Session — der Agent-Dienst bleibt für dich aktiv]\n", flush=True)
                _reset_session(messages, root)
                return True
            return False
        if low in ("/neu", "/new", "/session-neu"):
            print("\n[Session zurückgesetzt]\n", flush=True)
            _reset_session(messages, root)
            return True
        if low in ("/hilfe", "/help"):
            print(_help_de(chamber=chamber))
            return True
        if chamber and low in ("/diene", "/serve", "/ressourcen-voll"):
            try:
                from analytics.alpha_model_king_resources import handle_serve_command

                print("[König · alle Ressourcen]\n")
                doc = handle_serve_command(root, text)
                print(doc.get("reply_de") or "(keine Antwort)")
                messages.append({"role": "user", "content": text})
                messages.append({"role": "assistant", "content": str(doc.get("reply_de") or "")[:8000]})
                return True
            except Exception as exc:
                print(f"[Diene FEHLER] {exc}")
            return True
        if chamber and low in ("/könig", "/koenig", "/king", "/kontrolle", "/handoff"):
            try:
                from analytics.alpha_model_king_handoff import format_handoff_de

                print(format_handoff_de(root))
            except Exception as exc:
                print(f"[König-Handoff] {exc}")
            return True
        if chamber and (low.startswith("/cursor") or low == "/cursor-bridge"):
            try:
                from analytics.alpha_model_cursor_bridge import handle_cursor_bridge_command

                print("[Cursor ↔ König Bridge]\n")
                doc = handle_cursor_bridge_command(root, text)
                print(doc.get("reply_de") or "(keine Antwort)")
                messages.append({"role": "user", "content": text})
                messages.append({"role": "assistant", "content": str(doc.get("reply_de") or "")[:4000]})
                return True
            except Exception as exc:
                print(f"[Cursor-Bridge FEHLER] {exc}")
            return True
        if chamber:
            try:
                from analytics.alpha_model_self_uninstall import (
                    handle_self_uninstall_command,
                    is_self_uninstall_command,
                )

                if is_self_uninstall_command(text):
                    print("[Maschinen-Masterprompt]\n")
                    doc = handle_self_uninstall_command(root, text)
                    print(doc.get("reply_de") or doc.get("headline_de") or doc.get("error_de"))
                    if doc.get("next_de"):
                        print(f"\n— Nächster Schritt: {doc['next_de']}")
                    messages.append({"role": "user", "content": text})
                    messages.append({"role": "assistant", "content": str(doc.get("reply_de") or "")[:4000]})
                    return True
            except Exception as exc:
                print(f"[Self-Uninstall FEHLER] {exc}")
                return True
            try:
                from analytics.r3_ki_web import (
                    handle_web_command,
                    is_internet_question,
                    is_web_command,
                    reply_internet_capabilities,
                )

                if is_web_command(text):
                    print("[Internet]\n")
                    doc = handle_web_command(root, text)
                    print(doc.get("reply_de") or doc.get("message_de") or "(keine Antwort)")
                    messages.append({"role": "user", "content": text})
                    messages.append({"role": "assistant", "content": str(doc.get("reply_de") or "")[:4000]})
                    return True
                if is_internet_question(text):
                    print("[Internet · Status & Befehle]\n")
                    doc = reply_internet_capabilities(root, text)
                    print(doc.get("reply_de") or "(keine Antwort)")
                    messages.append({"role": "user", "content": text})
                    messages.append({"role": "assistant", "content": str(doc.get("reply_de") or "")[:4000]})
                    return True
            except Exception as exc:
                print(f"[Internet FEHLER] {exc} — Fallback auf Chat")
            try:
                from analytics.alpha_model_advisor_bridge import handle_bridge_command

                if text.strip().lower().startswith(("/berater-key", "/advisor-key", "/key")):
                    print("[Berater-Bridge]\n")
                    doc = handle_bridge_command(root, text)
                    print(doc.get("reply_de") or doc.get("message_de") or "(keine Antwort)")
                    messages.append({"role": "user", "content": text})
                    messages.append({"role": "assistant", "content": str(doc.get("reply_de") or "")[:4000]})
                    return True
            except Exception as exc:
                print(f"[Berater-Bridge FEHLER] {exc}")
            try:
                from analytics.alpha_model_advisor_bridge import load_openai_key_into_env

                load_openai_key_into_env(root)
            except Exception:
                pass
            try:
                from analytics.r3_external_advisor import handle_advisor_command, is_advisor_command

                if is_advisor_command(text):
                    print("[Berater · /kombi /tipp]\n")
                    doc = handle_advisor_command(root, text)
                    print(doc.get("reply_de") or doc.get("message_de") or "(keine Antwort)")
                    messages.append({"role": "user", "content": text})
                    messages.append({"role": "assistant", "content": str(doc.get("reply_de") or "")[:4000]})
                    return True
            except Exception as exc:
                print(f"[Berater FEHLER] {exc} — Fallback auf Chat")
            try:
                from analytics.alpha_model_coding_bridge import handle_coding_command, try_auto_coding

                if low in ("/bau", "/build") or low.startswith(("/bau ", "/build ", "/beitrag ", "/contribute ")):
                    try:
                        from analytics.alpha_model_entfaltung_32b import preload_build_model, tier_status

                        ts = tier_status(root)
                        print(f"[Coding-Kernel · Ideal-32B · {ts.get('resolved_build_model')}]\n")
                        pre = preload_build_model(root)
                        if pre.get("preloaded"):
                            print(f"(GPU preload OK · num_ctx {pre.get('num_ctx')})\n")
                    except Exception:
                        print("[Coding-Kernel]\n")
                    doc = handle_coding_command(root, text)
                    print(doc.get("reply_de") or doc.get("error_de") or "(keine Antwort)")
                    messages.append({"role": "user", "content": text})
                    messages.append({"role": "assistant", "content": str(doc.get("reply_de") or "")[:4000]})
                    return True
                auto = try_auto_coding(root, text)
                if auto is not None:
                    print("[Coding-Kernel · Auto]\n")
                    print(auto.get("reply_de") or "(keine Antwort)")
                    messages.append({"role": "user", "content": text})
                    messages.append({"role": "assistant", "content": str(auto.get("reply_de") or "")[:4000]})
                    return True
                try:
                    from analytics.alpha_model_chat_agent import should_route_to_bau

                    if should_route_to_bau(text):
                        try:
                            from analytics.alpha_model_entfaltung_32b import preload_build_model, tier_status

                            ts = tier_status(root)
                            print(
                                f"[Coding-Kernel · Auto · Ideal-32B · {ts.get('resolved_build_model')}]\n"
                            )
                            preload_build_model(root)
                        except Exception:
                            print("[Coding-Kernel · Routing — Code-Auftrag erkannt]\n")
                        doc = handle_coding_command(root, f"/bau {text}")
                        print(doc.get("reply_de") or doc.get("error_de") or "(keine Antwort)")
                        messages.append({"role": "user", "content": text})
                        messages.append({"role": "assistant", "content": str(doc.get("reply_de") or "")[:4000]})
                        return True
                except Exception:
                    pass
            except Exception as exc:
                print(f"[Coding-Kernel FEHLER] {exc}")
                return True
        kernel_cmd = SLASH.get(low.split()[0] if low.startswith("/") else "")
        if kernel_cmd or low.startswith("/kernel "):
            cmd = kernel_cmd or text.split(maxsplit=1)[1].strip()
            print(f"[ai_kernel {cmd}]\n")
            out = run_kernel_command(root, cmd)
            print(out)
            messages.append({"role": "user", "content": f"/kernel {cmd}\n{out[:4000]}"})
            messages.append(
                {
                    "role": "assistant",
                    "content": f"Befehl `{cmd}` ausgeführt. Kurze Zusammenfassung für den Nutzer.",
                }
            )
            try:
                reply, _ = chat_completion(root, messages[-2:], model=model)
                print(f"\nAuto: {reply}\n")
                messages.append({"role": "assistant", "content": reply})
            except Exception as exc:
                print(f"(Zusammenfassung übersprungen: {exc})")
            return True

        messages.append({"role": "user", "content": text})
        reply = ""
        if chamber:
            try:
                from analytics.alpha_model_chat_agent import run_chat_agent

                print("[König · Chat-Agent …]", flush=True)
                doc = run_chat_agent(root, text, history=messages[1:])
                reply = str(doc.get("reply_de") or "")
            except Exception as exc:
                print(f"[König FEHLER] {exc}")
                messages.pop()
                return True
            if not reply:
                print("[König] Keine Antwort — präzisiere die Frage oder /bau für Code.")
                messages.pop()
                return True
        else:
            try:
                print("[…] Antwort vorbereiten (Modell kann 10–90s brauchen) …", flush=True)
                reply, _ = chat_completion(root, messages, model=model)
            except Exception as exc:
                print(f"[FEHLER] {exc}")
                messages.pop()
                return True
        print(f"\nAuto: {reply}\n")
        if chamber:
            if serve_mode:
                print(
                    "(Agent-Dienst aktiv — weiter eingeben · /quit = neue Session · /dienst-stop = Stopp)\n",
                    flush=True,
                )
            else:
                print("(Session aktiv — weiter eingeben oder /quit)\n", flush=True)
        messages.append({"role": "assistant", "content": reply})
        try:
            from analytics.linux_operator_scope import log_operator_action

            log_operator_action(root, level="A", action="local_chat", result=text[:80], status="INFO")
        except Exception:
            pass
        return True

    if once:
        handle_line(once)
        return 0

    stop_serve = False

    def handle_line_with_serve(line: str) -> bool:
        nonlocal stop_serve
        low = line.strip().lower()
        if low in ("/dienst-stop", "/stop-serve", "/serve-stop", "/dienst-ende"):
            stop_serve = True
            return False
        return handle_line(line)

    while True:
        try:
            line = input("Du: ").strip()
        except EOFError:
            if serve_mode:
                print(
                    "\n[Eingabe beendet — Agent-Dienst startet neue Session …]\n",
                    flush=True,
                )
                return 1
            if chamber:
                print("\n(Session beendet — zum Weitermachen: alpha-model-agent)\n")
            else:
                print("\nTschüss.")
            break
        except KeyboardInterrupt:
            if serve_mode:
                print("\n[Unterbrochen — Agent bleibt aktiv. Weiter eingeben …]\n", flush=True)
                continue
            print("\nTschüss.")
            break
        if not handle_line_with_serve(line):
            break
    return 3 if stop_serve else 0


def main() -> int:
    p = argparse.ArgumentParser(description="Active Alpha lokaler Chat (Ollama)")
    p.add_argument("--model", default=None)
    p.add_argument("--once", default=None, help="Einzelne Frage, dann beenden")
    p.add_argument("--serve", action="store_true", help="Agent-Dienst: immer neu starten bis /dienst-stop")
    p.add_argument("--no-serve", action="store_true", help="Einmalige Session ohne Dienst-Schleife")
    p.add_argument("--health", action="store_true")
    args = p.parse_args()
    root = Path(__import__("os").environ.get("AA_PROJECT_ROOT", str(ROOT)))
    if args.health:
        from analytics.local_llm_bridge import health_report

        print(json.dumps(health_report(root), indent=2, ensure_ascii=False))
        return 0 if health_report(root).get("ready") else 1
    if args.once:
        return run_repl(root, model=args.model, once=args.once, serve_mode=False)
    use_serve = args.serve or not args.no_serve
    chamber = __import__("os").environ.get("AA_AGENT_CHAMBER", "").strip().lower() in ("1", "true", "yes")
    if use_serve and chamber:
        from analytics.alpha_model_agent_serve import run_agent_serve

        return run_agent_serve(root, repl_fn=run_repl, model=args.model)
    return run_repl(root, model=args.model, serve_mode=False)


if __name__ == "__main__":
    raise SystemExit(main())
