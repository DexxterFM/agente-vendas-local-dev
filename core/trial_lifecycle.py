"""Ciclo explícito do teste: nunca converte ou cobra sem confirmação humana.

O estado é persistido na memória comercial para que o painel e o worker usem a
mesma regra. A exportação de encerramento é um envelope autenticado e cifrado
com uma chave do próprio cofre da aplicação; ela não contém dados em claro.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

TRIAL_DAYS = 90
WARNING_DAYS = 10
DATA_GRACE_DAYS = 15


def _utc(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif value:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    else:
        result = datetime.now(timezone.utc)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _keystream(key: bytes, nonce: bytes, size: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < size:
        out.extend(hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(out[:size])


def encrypt_export(raw: dict[str, Any], secret: str) -> str:
    """Cifra e autentica um snapshot JSON sem registrar o conteúdo em claro."""
    salt, nonce = os.urandom(16), os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 210_000, 32)
    plain = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    cipher = bytes(a ^ b for a, b in zip(plain, _keystream(key, nonce, len(plain))))
    tag = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    return json.dumps({
        "version": 1,
        "algorithm": "PBKDF2-SHA256/HMAC-SHA256 stream envelope",
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(cipher).decode("ascii"),
        "tag": base64.b64encode(tag).decode("ascii"),
    }, separators=(",", ":"))


class TrialLifecycle:
    """Estado do teste de uma conta, com transições sem cobrança implícita."""

    def __init__(self, memory):
        self.memory = memory

    def _key(self, account_id: str) -> str:
        clean = "".join(ch for ch in str(account_id or "default") if ch.isalnum() or ch in "._-")[:80]
        return "sales.trial.lifecycle:" + (clean or "default")

    def _secret(self) -> str:
        secret = self.memory.get_setting("sales.trial.export_secret", "")
        if not secret:
            secret = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
            self.memory.set_setting("sales.trial.export_secret", secret)
        return secret

    def _read(self, account_id: str) -> dict[str, Any]:
        raw = self.memory.get_setting(self._key(account_id), "")
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    def _write(self, account_id: str, state: dict[str, Any]) -> dict[str, Any]:
        self.memory.set_setting(self._key(account_id), json.dumps(state, ensure_ascii=False, separators=(",", ":")))
        return state

    def start(self, account_id: str = "default", activated_at: str | datetime | None = None) -> dict[str, Any]:
        started = _utc(activated_at)
        state = {
            "account_id": str(account_id or "default"),
            "status": "active",
            "activated_at": _iso(started),
            "trial_ends_at": _iso(started + timedelta(days=TRIAL_DAYS)),
            "warning_at": _iso(started + timedelta(days=TRIAL_DAYS - WARNING_DAYS)),
            "data_grace_ends_at": _iso(started + timedelta(days=TRIAL_DAYS + DATA_GRACE_DAYS)),
            "warning_sent_at": "",
            "exported_at": "",
            "deleted_at": "",
            "continuation_requested_at": "",
        }
        self.memory.audit("trial.started", "trial:" + str(account_id), "ok", "automatic_charge=false")
        return self._write(account_id, state)

    def request_continuation(self, account_id: str = "default") -> dict[str, Any]:
        state = self._read(account_id)
        if not state:
            raise ValueError("Nenhum teste ativo para esta conta.")
        if state.get("status") in {"active", "ending_soon"}:
            state["status"] = "continuation_requested"
            state["continuation_requested_at"] = _iso(datetime.now(timezone.utc))
            self.memory.audit("trial.continuation_requested", "trial:" + str(account_id), "ok", "payment_required=true; automatic_charge=false")
            return self._write(account_id, state)
        return state

    def confirm_payment(self, account_id: str = "default") -> dict[str, Any]:
        state = self._read(account_id)
        if not state:
            raise ValueError("Nenhum ciclo de teste encontrado.")
        state["status"] = "paid_active"
        state["payment_confirmed_at"] = _iso(datetime.now(timezone.utc))
        self.memory.audit("trial.payment_confirmed", "trial:" + str(account_id), "ok", "human_confirmation=true")
        return self._write(account_id, state)

    def status(self, account_id: str = "default", now: str | datetime | None = None, raw_data: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self._read(account_id)
        if not state:
            return {"account_id": account_id, "status": "not_started", "automatic_charge": False}
        moment = _utc(now)
        if state.get("status") == "active" and moment >= _utc(state["warning_at"]):
            state["status"] = "ending_soon"
            state["warning_sent_at"] = state.get("warning_sent_at") or _iso(moment)
            self.memory.audit("trial.warning_due", "trial:" + str(account_id), "queued", "days_remaining=10; automatic_charge=false")
        if state.get("status") in {"active", "ending_soon", "continuation_requested"} and moment >= _utc(state["trial_ends_at"]):
            state["status"] = "expired_locked"
            state["access_locked_at"] = state.get("access_locked_at") or _iso(moment)
            state["deletion_at"] = state.get("deletion_at") or _iso(moment + timedelta(days=DATA_GRACE_DAYS))
            if not state.get("exported_at"):
                payload = raw_data or {"account_id": account_id, "exported_for": "customer_recovery"}
                state["encrypted_export"] = encrypt_export(payload, self._secret())
                state["exported_at"] = _iso(moment)
            self.memory.audit("trial.expired", "trial:" + str(account_id), "locked", "data_export_encrypted=true; deletion_grace_days=15")
        if state.get("status") == "expired_locked" and moment >= _utc(state["deletion_at"]):
            state["status"] = "deleted"
            state["deleted_at"] = state.get("deleted_at") or _iso(moment)
            state.pop("encrypted_export", None)
            self.memory.audit("trial.data_deleted", "trial:" + str(account_id), "ok", "retention_window_elapsed=true")
        state["automatic_charge"] = False
        return self._write(account_id, state)

    def warning_message(self, state: dict[str, Any]) -> str:
        return ("Seu teste gratuito termina em 10 dias. Não haverá cobrança automática. "
                "Se quiser continuar, responda ‘quero continuar’ e enviaremos as opções para você.")
