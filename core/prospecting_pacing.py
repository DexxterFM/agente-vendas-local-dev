"""Ritmo persistente para contatos de prospecção ativa.

Uma rodada só pode começar depois da janela calculada pela roleta anterior.
O estado fica no banco do agente, portanto reiniciar a interface não reduz o
intervalo entre contatos.
"""
import random
import time


class ProspectingPacing:
    MIN_INTERVAL_SECONDS = 300

    def __init__(self, memory, clock=time.time, dice=None, jitter=None):
        self.memory = memory
        self.clock = clock
        self.dice = dice or (lambda: random.SystemRandom().randint(1, 6))
        self.jitter = jitter or (lambda: random.SystemRandom().randint(15, 90))

    def status(self):
        now = float(self.clock())
        next_at = float(self.memory.get_setting("sales.prospecting.next_at", "0") or 0)
        return {
            "ready": now >= next_at,
            "next_at": next_at,
            "wait_seconds": max(0, int(next_at - now)),
        }

    def reserve_round(self, kind="instagram_outreach", target=""):
        current = self.status()
        if not current["ready"]:
            return {"reserved": False, **current}
        roll = max(1, min(6, int(self.dice())))
        # A roleta influencia a pausa; mesmo o menor resultado fica acima de
        # cinco minutos.  O jitter impede uma cadência mecânica.
        interval = self.MIN_INTERVAL_SECONDS + (roll * 45) + max(15, int(self.jitter()))
        now = float(self.clock())
        next_at = now + interval
        self.memory.set_setting("sales.prospecting.next_at", str(next_at))
        self.memory.set_setting("sales.prospecting.last_roll", str(roll))
        self.memory.audit(
            "sales.prospecting.roll",
            str(target or kind)[:120],
            "ok",
            f"kind={str(kind)[:80]}; die={roll}; next_interval_seconds={interval}",
        )
        return {
            "reserved": True,
            "ready": True,
            "roll": roll,
            "interval_seconds": interval,
            "next_at": next_at,
            "wait_seconds": interval,
        }
