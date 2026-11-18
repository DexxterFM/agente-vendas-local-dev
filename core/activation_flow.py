"""Fluxo de ativação de teste gratuito do ERP Clínica TEA.

O link enviado pelo Instagram leva a um formulário público onde o lead informa
dados básicos da empresa (nome, CNPJ, email, senha). Após o envio, o sistema:

1. Valida CNPJ e email;
2. Registra a solicitação de ativação na memória comercial;
3. Ativa o teste de 3 meses via TrialLifecycle (sem cobrança automática);
4. Provisiona o registro de banco de dados/perfil inicial para a empresa;
5. Armazena a senha de forma cifrada (hash) para primeiro acesso.

Todos os dados são persistidos no mesmo SQLite da memória comercial.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import load_config
from core.memory import Memory
from core.trial_lifecycle import TrialLifecycle

CNPJ_DIGITS = re.compile(r"\D")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_cnpj(cnpj: str) -> str:
    return CNPJ_DIGITS.sub("", cnpj or "")


def _validate_cnpj(cnpj: str) -> bool:
    digits = _clean_cnpj(cnpj)
    if len(digits) != 14 or digits == digits[0] * 14:
        return False

    def calc(digits: str, weights: list[int]) -> int:
        total = sum(int(d) * w for d, w in zip(digits, weights))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    if int(digits[12]) != calc(digits[:12], weights1):
        return False
    if int(digits[13]) != calc(digits[:13], weights2):
        return False
    return True


def _validate_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""))


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 210_000)
    return f"pbkdf2_sha256$210000${salt}$${digest.hex()}"


@dataclass
class ActivationRequest:
    company_name: str
    cnpj: str
    email: str
    password: str
    phone: str = ""
    plan: str = "clinic_multi"
    utm_source: str = ""
    utm_campaign: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActivationResult:
    ok: bool
    activation_code: str
    company_name: str
    cnpj: str
    email: str
    plan: str
    trial_ends_at: str
    message: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ActivationFlow:
    """Orquestra o cadastro e ativação de uma nova conta de teste."""

    SETTING_PREFIX = "sales.activation."

    def __init__(self, memory: Memory):
        self.memory = memory
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self.memory.db.execute(
            """
            create table if not exists activation_requests (
                id integer primary key,
                activation_code text not null unique,
                company_name text not null,
                cnpj text not null,
                email text not null,
                phone text,
                plan text not null,
                password_hash text not null,
                status text not null default 'pending',
                trial_ends_at text,
                activated_at text,
                utm_source text,
                utm_campaign text,
                created_at text not null
            )
            """
        )
        self.memory.db.execute(
            "create index if not exists idx_activation_code on activation_requests(activation_code)"
        )
        self.memory.db.execute(
            "create index if not exists idx_activation_cnpj on activation_requests(cnpj)"
        )
        self.memory.db.execute(
            "create index if not exists idx_activation_email on activation_requests(email)"
        )
        self.memory.db.commit()

    def _db_path_for_company(self, cnpj: str) -> str:
        """Caminho do banco de dados provisionado para a empresa."""
        clean = re.sub(r"\D", "", cnpj or "")
        base = Path(load_config().db_path).parent
        return str(base / f"erp_clinic_tea_{clean}.sqlite3")

    def register(self, req: ActivationRequest) -> ActivationResult:
        """Registra uma solicitação de ativação e ativa o teste de 3 meses."""
        if not req.company_name or not req.company_name.strip():
            return ActivationResult(False, "", "", "", "", "", "", "Informe o nome da empresa.", "company_name_required")
        if not _validate_cnpj(req.cnpj):
            return ActivationResult(False, "", "", "", "", "", "", "CNPJ inválido.", "invalid_cnpj")
        if not _validate_email(req.email):
            return ActivationResult(False, "", "", "", "", "", "", "E-mail inválido.", "invalid_email")
        if not req.password or len(req.password) < 6:
            return ActivationResult(False, "", "", "", "", "", "", "A senha deve ter pelo menos 6 caracteres.", "weak_password")

        clean_cnpj = _clean_cnpj(req.cnpj)
        existing = self.memory.db.execute(
            "select id from activation_requests where cnpj=? or email=?",
            (clean_cnpj, req.email.lower()),
        ).fetchone()
        if existing:
            return ActivationResult(False, "", "", "", "", "", "", "CNPJ ou e-mail já cadastrado.", "duplicate")

        activation_code = "ACT" + secrets.token_urlsafe(16)
        password_hash = _hash_password(req.password)
        trial = TrialLifecycle(self.memory)
        trial_state = trial.start(account_id=clean_cnpj)
        trial_ends_at = trial_state.get("trial_ends_at", "")

        self.memory.db.execute(
            """
            insert into activation_requests
            (activation_code, company_name, cnpj, email, phone, plan, password_hash,
             status, trial_ends_at, utm_source, utm_campaign, created_at)
            values (?, ?, ?, ?, ?, ?, ?, 'provisioned', ?, ?, ?, ?)
            """,
            (
                activation_code,
                req.company_name.strip(),
                clean_cnpj,
                req.email.lower().strip(),
                req.phone.strip(),
                req.plan,
                password_hash,
                trial_ends_at,
                req.utm_source,
                req.utm_campaign,
                _utc_now(),
            ),
        )
        self.memory.db.commit()

        # Provisionamento de banco de dados/perfil inicial da empresa.
        company_db = self._db_path_for_company(clean_cnpj)
        self.memory.db.execute(
            """
            insert or replace into settings(key, value, updated_at)
            values (?, ?, ?)
            """,
            (
                f"sales.activation.company_db:{clean_cnpj}",
                company_db,
                _utc_now(),
            ),
        )
        self.memory.db.execute(
            """
            insert or replace into settings(key, value, updated_at)
            values (?, ?, ?)
            """,
            (
                f"sales.activation.company_profile:{clean_cnpj}",
                json.dumps({
                    "company_name": req.company_name.strip(),
                    "cnpj": clean_cnpj,
                    "email": req.email.lower().strip(),
                    "phone": req.phone.strip(),
                    "plan": req.plan,
                    "db_path": company_db,
                    "status": "provisioned",
                    "created_at": _utc_now(),
                }, ensure_ascii=False),
                _utc_now(),
            ),
        )
        self.memory.db.commit()

        self.memory.audit(
            "activation.registered",
            f"activation:{activation_code}",
            "ok",
            f"cnpj={clean_cnpj}; email={req.email}; plan={req.plan}; trial_ends={trial_ends_at}",
        )

        return ActivationResult(
            ok=True,
            activation_code=activation_code,
            company_name=req.company_name.strip(),
            cnpj=clean_cnpj,
            email=req.email.lower().strip(),
            plan=req.plan,
            trial_ends_at=trial_ends_at,
            message=(
                f"Sua empresa {req.company_name} foi cadastrada com sucesso. "
                "O teste gratuito de 3 meses do ERP Clínica TEA Multiprofissional foi ativado. "
                "Use o código e a senha informados para acessar seu ambiente provisionado."
            ),
        )

    def status(self, activation_code: str | None = None, cnpj: str | None = None, email: str | None = None) -> dict[str, Any] | None:
        query = "select * from activation_requests where 1=1"
        params: list[Any] = []
        if activation_code:
            query += " and activation_code=?"
            params.append(activation_code)
        if cnpj:
            query += " and cnpj=?"
            params.append(_clean_cnpj(cnpj))
        if email:
            query += " and email=?"
            params.append(email.lower().strip())
        row = self.memory.db.execute(query, params).fetchone()
        if not row:
            return None
        columns = [d[0] for d in self.memory.db.execute(query, params).description]
        return dict(zip(columns, row))

    def list_all(self) -> list[dict[str, Any]]:
        rows = self.memory.db.execute(
            "select activation_code, company_name, cnpj, email, plan, status, trial_ends_at, created_at "
            "from activation_requests order by created_at desc"
        ).fetchall()
        columns = [d[0] for d in self.memory.db.execute(
            "select activation_code, company_name, cnpj, email, plan, status, trial_ends_at, created_at "
            "from activation_requests order by created_at desc limit 1"
        ).description]
        return [dict(zip(columns, row)) for row in rows]
