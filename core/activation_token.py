"""Gerenciamento de tokens neutros de ativação do ERP Clínica TEA.

Os tokens são códigos de uso único enviados aos leads após o "eu quero".
Cada token só pode ser consumido uma vez e nunca é repetido para clientes
diferentes. Expiram automaticamente após 30 dias ou podem ser revogados.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from core.config import load_config
from core.memory import Memory

TOKEN_PREFIX = "ERPDEMO-"
TOKEN_REGEX = re.compile(r"^ERPDEMO-[0-9A-Fa-f]{8,}-[A-Za-z0-9_-]{4,}(?:-[A-Za-z0-9_-]{4,})*$")
EXPIRY_DAYS = 30


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class TokenInfo:
    code: str
    used: bool
    used_by: str | None
    used_at: str | None
    expires_at: str
    created_at: str
    edition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ActivationTokenManager:
    """Gerencia tokens de ativação de uso único."""

    def __init__(self, memory: Memory):
        self.memory = memory
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self.memory.db.execute(
            """
            create table if not exists activation_tokens (
                code text primary key,
                used integer not null default 0,
                used_by text,
                used_at text,
                expires_at text not null,
                created_at text not null,
                edition text
            )
            """
        )
        try:
            self.memory.db.execute("alter table activation_tokens add column edition text")
            self.memory.db.commit()
        except Exception:
            pass
        self.memory.db.execute(
            "create index if not exists idx_activation_tokens_used on activation_tokens(used)"
        )
        self.memory.db.execute(
            "create index if not exists idx_activation_tokens_expires on activation_tokens(expires_at)"
        )
        self.memory.db.commit()

    def _is_valid_format(self, token: str) -> bool:
        return bool(TOKEN_REGEX.match(token or ""))

    def _normalize_token(self, token: str) -> str:
        token = (token or "").strip()
        if token.startswith(TOKEN_PREFIX):
            return token
        return TOKEN_PREFIX + token

    def register_tokens(self, tokens: list[str], edition: str | None = None) -> dict[str, Any]:
        """Registra uma lista de tokens no banco. Retorna resumo."""
        now = _utc_now()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=EXPIRY_DAYS)).isoformat()
        registered = 0
        skipped = 0
        for raw in tokens:
            token = self._normalize_token(raw)
            if not self._is_valid_format(token):
                skipped += 1
                continue
            existing = self.memory.db.execute(
                "select code from activation_tokens where code=?",
                (token,),
            ).fetchone()
            if existing:
                skipped += 1
                continue
            self.memory.db.execute(
                """
                insert into activation_tokens
                (code, used, used_by, used_at, expires_at, created_at, edition)
                values (?, 0, NULL, NULL, ?, ?, ?)
                """,
                (token, expires_at, now, edition),
            )
            registered += 1
        self.memory.db.commit()
        self.memory.audit(
            "activation.tokens.registered",
            "activation.tokens",
            "ok",
            f"registered={registered}; skipped={skipped}; expiry_days={EXPIRY_DAYS}",
        )
        return {"registered": registered, "skipped": skipped, "expires_at": expires_at}

    def _cleanup_expired(self) -> int:
        """Marca tokens expirados como usados (não consumíveis)."""
        now = _utc_now()
        rows = self.memory.db.execute(
            "select code from activation_tokens where used=0 and expires_at < ?",
            (now,),
        ).fetchall()
        count = 0
        for (code,) in rows:
            self.memory.db.execute(
                "update activation_tokens set used=1, used_by='expired', used_at=? where code=?",
                (now, code),
            )
            count += 1
        if count:
            self.memory.db.commit()
        return count

    def _available_token(self) -> dict[str, Any] | None:
        """Devolve um token não usado e não expirado."""
        self._cleanup_expired()
        row = self.memory.db.execute(
            """
            select code, expires_at, created_at
            from activation_tokens
            where used=0
            order by created_at asc
            limit 1
            """
        ).fetchone()
        if not row:
            return None
        return {
            "code": row[0],
            "expires_at": row[1],
            "created_at": row[2],
        }

    def consume_token(self, lead_id: int, lead_name: str | None = None) -> dict[str, Any] | None:
        """Reserva e consome o próximo token disponível para um lead. Devolve o código em claro."""
        token = self._available_token()
        if not token:
            return None
        now = _utc_now()
        used_by = str(lead_name or f"lead:{lead_id}")
        self.memory.db.execute(
            """
            update activation_tokens
            set used=1, used_by=?, used_at=?
            where code=?
            """,
            (used_by, now, token["code"]),
        )
        self.memory.db.commit()
        self.memory.audit(
            "activation.token.consumed",
            f"token:{token['code'][:12]}...",
            "ok",
            f"lead_id={lead_id}; lead_name={used_by}",
        )
        return {
            "consumed": True,
            "token": token["code"],
            "lead_id": lead_id,
            "used_by": used_by,
            "consumed_at": now,
        }

    def list_all(self) -> list[dict[str, Any]]:
        self._cleanup_expired()
        rows = self.memory.db.execute(
            """
            select code, used, used_by, used_at, expires_at, created_at, edition
            from activation_tokens
            order by created_at asc
            """
        ).fetchall()
        columns = [d[0] for d in self.memory.db.execute(
            "select code, used, used_by, used_at, expires_at, created_at, edition "
            "from activation_tokens limit 1"
        ).description]
        return [dict(zip(columns, row)) for row in rows]

    def stats(self) -> dict[str, Any]:
        self._cleanup_expired()
        total = self.memory.db.execute(
            "select count(*) from activation_tokens"
        ).fetchone()[0]
        used = self.memory.db.execute(
            "select count(*) from activation_tokens where used=1"
        ).fetchone()[0]
        available = total - used
        expired = self.memory.db.execute(
            "select count(*) from activation_tokens where used=0 and expires_at < ?",
            (_utc_now(),),
        ).fetchone()[0]
        return {
            "total": total,
            "used": used,
            "available": available,
            "expired": expired,
            "expiry_days": EXPIRY_DAYS,
        }
