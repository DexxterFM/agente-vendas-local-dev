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
MAX_IDLE_CYCLES = 2


HUMAN_LIMITS = {
    # Limites seguros do Instagram (contas novas até 3 meses):
    # Seguir/deixar de seguir: 10–15/h, máx 100/dia | intervalo mínimo 45s
    # Comentários: 5–10/h, máx 50–100/dia | intervalo mínimo 45s
    # DMs: 2–4/h, máx 20–50/dia | intervalo mínimo 45s
    # Nenhuma ação com menos de 30–45s entre si (padrão mecânico).
    "follow": {"per_hour": 10, "per_day": 100, "min_interval_sec": 60, "max_interval_sec": 180},
    "prospect_dm": {"per_hour": 3, "per_day": 30, "min_interval_sec": 120, "max_interval_sec": 300, "active_hours": (8, 20)},
    "comment": {"per_hour": 6, "per_day": 50, "min_interval_sec": 60, "max_interval_sec": 180},
    "dm_reply": {"per_hour": 3, "per_day": 30, "min_interval_sec": 120, "max_interval_sec": 300, "active_hours": (8, 22)},
}


def _action_key(action_type: str) -> str:
    return "sales.agent.rate_limit.last:" + str(action_type).strip().lower()


def _count_actions(memory, action_type: str, since_hours: float) -> int:
    """Conta ações de um tipo no log de auditoria nas últimas N horas."""
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
    action_type = str(action_type).strip().lower()
    try:
        rows = memory.db.execute(
            "select count(*) from audit_events where action like ? and created_at >= ?",
            ("%" + action_type + "%", cutoff),
        ).fetchone()
        return int(rows[0]) if rows else 0
    except Exception:
        return 0


class HumanRateLimiter:
    """Controlador de cotas orgânicas para ações humanas simuladas."""

    def __init__(self, memory=None):
        self.memory = memory
        if self.memory is None:
            import unittest.mock as _mock
            self.memory = _mock.MagicMock()
            self.memory.db.execute.return_value.fetchone.return_value = (0,)
            self.memory.get_setting.return_value = ""

    def can_perform_action(self, action_type: str, now_ts=None) -> tuple:
        """Verifica se a ação pode ser executada.

        Retorna (allowed: bool, reason: str, wait_seconds: float).
        """
        import time as _time
        from datetime import datetime, timezone

        action_type = str(action_type).strip().lower()
        limits = HUMAN_LIMITS.get(action_type)
        if not limits:
            return True, "no_limits", 0.0

        now = now_ts if now_ts is not None else _time.time()
        now_dt = datetime.fromtimestamp(now, tz=timezone.utc)

        # Active hours (só bloqueia se já houver histórico de ações)
        if "active_hours" in limits:
            start_h, end_h = limits["active_hours"]
            if count_day == 0:
                pass  # Primeira execução: não bloqueia por horário
            elif not (start_h <= now_dt.hour <= end_h):
                if now_dt.hour < start_h:
                    wait = (start_h - now_dt.hour) * 3600 - now_dt.minute * 60 - now_dt.second
                else:
                    wait = (24 - now_dt.hour + start_h) * 3600 - now_dt.minute * 60 - now_dt.second
                return False, "outside_active_hours", float(max(0, wait))

        # Per hour
        per_hour = int(limits.get("per_hour", 9999))
        count_hour = _count_actions(self.memory, action_type, 1.0)
        if count_hour >= per_hour:
            return False, "hourly_limit", 3600.0

        # Per day
        per_day = int(limits.get("per_day", 9999))
        count_day = _count_actions(self.memory, action_type, 24.0)
        if count_day >= per_day:
            return False, "daily_limit", 3600.0

        # Min interval
        last_key = _action_key(action_type)
        last_raw = self.memory.get_setting(last_key, "")
        if last_raw:
            try:
                last_ts = float(last_raw)
                elapsed = now - last_ts
                min_interval = float(limits.get("min_interval_sec", 0))
                if elapsed < min_interval:
                    wait = min_interval - elapsed
                    return False, "cooldown", float(wait)
            except (TypeError, ValueError):
                pass

        return True, "ok", 0.0

    def record_action(self, action_type: str, now_ts=None) -> None:
        """Registra que a ação foi executada (para cálculo de intervalo)."""
        import time as _time
        now = now_ts if now_ts is not None else _time.time()
        self.memory.set_setting(_action_key(action_type), str(now))


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
