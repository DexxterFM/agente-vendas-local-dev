"""Fila alternada entre atendimento comercial e prospecção ativa.

Os dois modos usam o mesmo navegador persistente. Rodá-los no mesmo ciclo faz
com que a leitura de DMs e a varredura do feed compitam pelo mesmo documento.
Este módulo guarda qual modo está no turno, alterna quando um job é concluído
e também após alguns ciclos sem trabalho, para que nenhum dos dois fique preso.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

MODES = ("sales", "prospecting")
KEY_MODE = "sales.agent.job_mode"
KEY_IDLE = "sales.agent.job_mode_idle_cycles"
KEY_CHANGED = "sales.agent.job_mode_changed_at"
KEY_LAST_JOB = "sales.agent.job_mode_last_job"
MAX_IDLE_CYCLES = 4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def status(memory: Any) -> dict[str, Any]:
    mode = str(memory.get_setting(KEY_MODE, "sales") or "sales").strip().lower()
    if mode not in MODES:
        mode = "sales"
        memory.set_setting(KEY_MODE, mode)
    try:
        idle = int(memory.get_setting(KEY_IDLE, "0") or 0)
    except (TypeError, ValueError):
        idle = 0
    raw = str(memory.get_setting(KEY_LAST_JOB, "") or "")
    last_job: dict[str, Any] = {}
    if raw.startswith("{"):
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                last_job = value
        except (TypeError, ValueError):
            last_job = {}
    return {
        "mode": mode,
        "next_mode": "prospecting" if mode == "sales" else "sales",
        "idle_cycles": max(0, idle),
        "max_idle_cycles": MAX_IDLE_CYCLES,
        "changed_at": str(memory.get_setting(KEY_CHANGED, "") or ""),
        "last_job": last_job,
    }


def switch(memory: Any, reason: str, actor: str = "system") -> dict[str, Any]:
    current = str(status(memory)["mode"])
    nxt = "prospecting" if current == "sales" else "sales"
    memory.set_setting(KEY_MODE, nxt)
    memory.set_setting(KEY_IDLE, "0")
    memory.set_setting(KEY_CHANGED, _now())
    memory.audit(
        "sales.agent.job_mode_switched",
        nxt,
        "ok",
        f"from={current}; reason={str(reason)[:120]}",
        actor=actor,
    )
    return status(memory)


def complete_job(memory: Any, mode: str, detail: str = "", actor: str = "system") -> dict[str, Any]:
    current = status(memory)
    if str(mode) != current["mode"]:
        # Um job do modo inativo nunca deve alterar a fila.
        return current
    memory.set_setting(KEY_LAST_JOB, json.dumps({
        "mode": current["mode"],
        "detail": str(detail)[:300],
        "at": _now(),
    }, ensure_ascii=False))
    return switch(memory, f"job-completed:{current['mode']}", actor=actor)


def idle_tick(memory: Any, mode: str, actor: str = "system") -> dict[str, Any]:
    current = status(memory)
    if str(mode) != current["mode"]:
        return current
    idle = current["idle_cycles"] + 1
    if idle >= MAX_IDLE_CYCLES:
        return switch(memory, f"idle-timeout:{current['mode']}", actor=actor)
    memory.set_setting(KEY_IDLE, str(idle))
    return status(memory)


def force_mode(memory: Any, mode: str, actor: str = "operator") -> dict[str, Any]:
    wanted = str(mode or "").strip().lower()
    if wanted not in MODES:
        raise ValueError("Modo inválido. Use sales ou prospecting.")
    current = status(memory)
    if wanted == current["mode"]:
        return current
    memory.set_setting(KEY_MODE, wanted)
    memory.set_setting(KEY_IDLE, "0")
    memory.set_setting(KEY_CHANGED, _now())
    memory.audit(
        "sales.agent.job_mode_forced",
        wanted,
        "ok",
        f"from={current['mode']}",
        actor=actor,
    )
    return status(memory)
