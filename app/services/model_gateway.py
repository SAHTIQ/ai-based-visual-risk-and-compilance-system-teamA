"""
QUANTA — Configurable AI Gateway
================================
Routes each chat turn to one of three strategies:

  auto         Primary grounded agent (planner → tools → composer). On any
               failure, transparently fail over to the local synthesis engine.
  primary_only Force the online agent; surface the error if it cannot answer.
  local_only   Force the local Context-Grounded Synthesis Engine (no network).

The agent is defined in ``app/services/agent.py``; the deterministic local
engine in ``app/services/fallback_engine.py``.
"""

import traceback

from app.services.agent import agent_answer, get_agent_status
from app.services.fallback_engine import run_local_fallback_synthesis
from app.services.llm_client import resolve_config

LOCAL_MODES = ("local_only", "force_local", "local")
PRIMARY_MODES = ("auto", "primary_only", "force_primary")


def run_ai_gateway(uid, user_message, routing_mode="auto", thread_id="default",
                   history=None):
    """
    Execute a chat turn using the selected routing strategy.

    Args:
        uid: Authenticated Firebase user id (scopes every tool query).
        user_message: The user's question.
        routing_mode: 'auto' | 'primary_only' | 'local_only'.
        thread_id: Chat thread id (telemetry only here).
        history: Optional list[{role, content}] recent turns for memory.

    Returns:
        dict with reply, tool_calls, widgets, sources_used, model_used,
        fallback_used, status, routing_mode, fallback_reason.
    """
    mode = (routing_mode or "auto").lower()
    history = history or []

    if mode in LOCAL_MODES:
        result = run_local_fallback_synthesis(uid, user_message)
        result["routing_mode"] = routing_mode
        result["fallback_reason"] = "user_requested_local"
        return result

    if mode in PRIMARY_MODES:
        try:
            primary = agent_answer(uid, user_message, history)
            if primary and primary.get("reply"):
                primary["routing_mode"] = routing_mode
                primary["fallback_reason"] = None
                return primary
            raise RuntimeError("Primary agent produced no answer.")
        except Exception as exc:
            message = str(exc)
            print(f"[ModelGateway] Primary agent failed: {message}")
            traceback.print_exc()

            if mode == "primary_only":
                cfg = resolve_config()
                return {
                    "reply": (
                        f"⚠️ The online model is unavailable right now ({message}). "
                        "Switch the routing mode to **Local** to use the grounded "
                        "offline engine."
                    ),
                    "tool_calls": [],
                    "widgets": [],
                    "sources_used": [],
                    "model_used": cfg.get("model", "unavailable"),
                    "fallback_used": False,
                    "fallback_reason": _categorize_error(message),
                    "status": "failed",
                }

            fallback = run_local_fallback_synthesis(uid, user_message)
            fallback["routing_mode"] = routing_mode
            fallback["fallback_used"] = True
            fallback["fallback_reason"] = _categorize_error(message)
            return fallback

    # Unknown mode → safest grounded default
    result = run_local_fallback_synthesis(uid, user_message)
    result["routing_mode"] = routing_mode
    result["fallback_reason"] = "unknown_routing_mode"
    return result


def _categorize_error(err_msg: str) -> str:
    """Map a raw error string to a stable, user-safe category label."""
    text = (err_msg or "").lower()
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "429" in text or "rate limit" in text or "quota" in text:
        return "rate_limit"
    if "401" in text or "403" in text or "unauthor" in text or "api key" in text:
        return "auth_error"
    if "connection" in text or "503" in text or "502" in text or "500" in text:
        return "provider_unavailable"
    return "invalid_output"


def gateway_status():
    """One-line provider/agent status for the boot log."""
    return get_agent_status()
