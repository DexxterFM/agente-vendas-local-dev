"""Memória SQLite com migrações idempotentes, CRM, consentimentos e auditoria."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import load_config
from core.tools import next_step_for_stage

_SECRET_PATTERN = re.compile(
    r"(?i)\b(token|senha|password|api[_-]?key|authorization|cookie|secret)\s*[:=]\s*([^\s,;]+)"
)
_SCHEMA_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_detail(detail: str, limit: int = 2000) -> str:
    value = _SECRET_PATTERN.sub(r"\1=[REDACTED]", str(detail or ""))
    value = value.replace("\r", " ").replace("\n", " ").strip()
    return value[:limit]


def _clean_text(text: str, limit: int = 4000) -> str:
    """Preserva quebras de linha para amostras, mas remove segredos óbvios."""
    value = _SECRET_PATTERN.sub(r"\1=[REDACTED]", str(text or ""))
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    return value[:limit]


class Memory:
    """Uma única conexão protegida por lock; compatível com o app e os testes antigos."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        path = Path(db_path) if db_path else load_config().db_path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db_path = path
        # Cada RPC usa sua própria conexão, mas a criação/migração do esquema
        # precisa ser serial para evitar SQLITE_BUSY na inicialização paralela.
        with _SCHEMA_LOCK:
            self.db = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
            with self._lock:
                self.db.execute("PRAGMA journal_mode=WAL")
                self.db.execute("PRAGMA foreign_keys=ON")
                self._create_schema()
                self._migrate()
                self._create_indexes()
                self.db.commit()

    # ------------------------------------------------------------------ schema
    def _create_schema(self) -> None:
        statements = (
            "create table if not exists messages (id integer primary key, role text, content text, created_at text)",
            "create table if not exists leads (id integer primary key, name text not null, contact text, stage text not null default 'new', notes text, created_at text not null)",
            "create table if not exists products (id integer primary key, name text not null, price real, active integer not null default 1, created_at text not null)",
            "create table if not exists opportunities (id integer primary key, lead_id integer not null, product_id integer, stage text not null default 'qualification', value real, next_action text, created_at text not null)",
            "create table if not exists followups (id integer primary key, lead_id integer not null, due_at text not null, task text not null, done integer not null default 0, created_at text not null)",
            "create table if not exists customers (id integer primary key, name text not null, contact text, company text, created_at text not null)",
            "create table if not exists conversations (id integer primary key, lead_id integer, role text not null, content text not null, created_at text not null)",
            "create table if not exists consents (id integer primary key, lead_id integer not null, channel text not null, granted integer not null, evidence text, created_at text not null)",
            "create table if not exists audit_events (id integer primary key, created_at text not null, actor text not null, action text not null, target text, status text not null, detail text)",
            "create table if not exists pending_actions (id integer primary key, created_at text not null, action text not null, payload text not null, rationale text, status text not null default 'pending', decided_at text, decision_note text)",
            "create table if not exists settings (key text primary key, value text not null, updated_at text not null)",
            "create table if not exists style_samples (id integer primary key, text text not null, source text not null default 'manual', created_at text not null)",
            "create table if not exists knowledge (id integer primary key, title text not null, content text not null, tags text, active integer not null default 1, created_at text not null)",
            # Memória dedicada de perfis do Instagram e do fluxo de diálogo.
            # Cada mensagem enviada é um passo do fluxo, registrada pelo hash do
            # texto normalizado para impedir reenvio (risco de denúncia por spam).
            "create table if not exists instagram_profiles (id integer primary key, username text not null unique, kind text not null default '', segment text not null default '', specialties text not null default '[]', thread_id text not null default '', stage text not null default '', current_stage text not null default 'OPENING', created_at text not null, updated_at text not null)",
            "create table if not exists instagram_profile_messages (id integer primary key, profile_id integer not null, flow_step text not null default '', hash text not null, text text not null default '', direction text not null default 'outgoing', sender_type text not null default 'agent', thread_id text not null default '', created_at text not null, unique(profile_id, hash))",
        )
        for statement in statements:
            self.db.execute(statement)

    def _ensure_column(self, table: str, column: str, declaration: str) -> None:
        columns = {row[1] for row in self.db.execute(f"pragma table_info({table})").fetchall()}
        if column not in columns:
            self.db.execute(f"alter table {table} add column {column} {declaration}")

    def _migrate(self) -> None:
        self._ensure_column("leads", "score", "integer not null default 0")
        self._ensure_column("leads", "next_action", "text")
        self._ensure_column("leads", "updated_at", "text")
        self._ensure_column("followups", "draft", "text")
        self._ensure_column("followups", "status", "text not null default 'draft'")
        self._ensure_column("followups", "channel", "text not null default 'manual'")
        self.db.execute("update leads set updated_at=created_at where updated_at is null or updated_at=''")
        rows = self.db.execute(
            "select id,stage from leads where next_action is null or next_action=''"
        ).fetchall()
        for lead_id, stage in rows:
            self.db.execute(
                "update leads set next_action=? where id=?",
                (next_step_for_stage(str(stage or "new")), lead_id),
            )
        self.db.execute("update followups set status='draft' where status is null or status=''")
        # Migração segura: colunas novas para memória de perfis do Instagram
        try:
            self.db.execute("alter table instagram_profiles add column current_stage text not null default 'OPENING'")
        except sqlite3.OperationalError:
            pass
        try:
            self.db.execute("alter table instagram_profile_messages add column sender_type text not null default 'agent'")
        except sqlite3.OperationalError:
            pass

    def _create_indexes(self) -> None:
        self.db.execute("create index if not exists idx_leads_stage on leads(stage)")
        self.db.execute("create index if not exists idx_messages_created on messages(id)")
        self.db.execute("create index if not exists idx_conversations_lead on conversations(lead_id, id)")
        self.db.execute("create index if not exists idx_followups_lead on followups(lead_id, id)")
        self.db.execute("create index if not exists idx_audit_created on audit_events(id)")
        self.db.execute("create index if not exists idx_pending_status on pending_actions(status, id)")
        self.db.execute("create index if not exists idx_style_samples on style_samples(id)")
        self.db.execute("create index if not exists idx_knowledge_active on knowledge(active, id)")
        self.db.execute("create index if not exists idx_ig_profiles_username on instagram_profiles(username)")
        self.db.execute("create index if not exists idx_ig_profile_messages on instagram_profile_messages(profile_id, id)")
        self.db.execute("create index if not exists idx_ig_profile_messages_hash on instagram_profile_messages(profile_id, hash)")

    # --------------------------------------------------------------- mensagens
    def add(self, role: str, content: str) -> None:
        with self._lock:
            self.db.execute(
                "insert into messages(role,content,created_at) values(?,?,?)",
                (role, content, _now()),
            )
            self.db.commit()

    def recent(self, limit: int = 12) -> list[tuple[str, str]]:
        with self._lock:
            rows = self.db.execute(
                "select role,content from messages order by id desc limit ?", (limit,)
            ).fetchall()
        return list(reversed(rows))

    def model_context(self, limit: int = 12, max_chars: int = 6000) -> list[dict[str, str]]:
        """Contexto curto e limitado; evita reenviar páginas gigantes ao modelo."""
        messages: list[dict[str, str]] = []
        budget = max_chars
        for role, content in reversed(self.recent(limit)):
            text = str(content or "")[:2000]
            if budget <= 0:
                break
            text = text[:budget]
            budget -= len(text)
            if role in {"user", "assistant"} and text.strip():
                messages.append({"role": role, "content": text})
        return list(reversed(messages))

    # ------------------------------------------------------------------- leads
    def add_lead(self, name: str, contact: str = "", notes: str = "") -> int:
        timestamp = _now()
        with self._lock:
            cursor = self.db.execute(
                "insert into leads(name,contact,stage,notes,created_at,score,next_action,updated_at) "
                "values(?,?,?,?,?,?,?,?)",
                (name, contact, "new", notes, timestamp, 0, next_step_for_stage("new"), timestamp),
            )
            lead_id = int(cursor.lastrowid)
            self.db.commit()
        self.audit("lead.created", f"lead:{lead_id}", "ok", f"contact_present={bool(contact)}")
        return lead_id

    def list_leads(self) -> list[tuple]:
        with self._lock:
            return self.db.execute(
                "select id,name,contact,stage,notes from leads order by id desc"
            ).fetchall()

    def list_leads_detailed(self) -> list[tuple]:
        with self._lock:
            return self.db.execute(
                "select id,name,contact,stage,score,coalesce(notes,''),"
                "coalesce(next_action,''),coalesce(updated_at,created_at),created_at "
                "from leads order by id desc"
            ).fetchall()

    def list_lead_choices(self) -> list[tuple[int, str, str]]:
        with self._lock:
            return self.db.execute(
                "select id,name,stage from leads order by name collate nocase"
            ).fetchall()

    def get_lead(self, lead_id: int) -> tuple | None:
        with self._lock:
            return self.db.execute(
                "select id,name,contact,stage,notes from leads where id=?", (lead_id,)
            ).fetchone()

    def get_lead_detail(self, lead_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self.db.execute(
                "select id,name,contact,stage,coalesce(notes,''),score,"
                "coalesce(next_action,''),coalesce(updated_at,created_at),created_at "
                "from leads where id=?",
                (lead_id,),
            ).fetchone()
        if not row:
            return None
        keys = (
            "id",
            "name",
            "contact",
            "stage",
            "notes",
            "score",
            "next_action",
            "updated_at",
            "created_at",
        )
        return dict(zip(keys, row))

    def update_lead_stage(
        self,
        lead_id: int,
        stage: str,
        notes: str = "",
        score: int | None = None,
        next_action: str | None = None,
    ) -> None:
        stage = stage if stage in {"new", "warm", "hot"} else "new"
        if score is None:
            match = re.search(r"score\s*=\s*(\d+)", notes or "")
            score = int(match.group(1)) if match else 0
        score = max(0, min(100, int(score)))
        action = next_action if next_action is not None else next_step_for_stage(stage)
        with self._lock:
            self.db.execute(
                "update leads set stage=?, notes=?, score=?, next_action=?, updated_at=? where id=?",
                (stage, notes, score, action, _now(), lead_id),
            )
            self.db.commit()
        self.audit("lead.qualified", f"lead:{lead_id}", "ok", f"stage={stage}; score={score}")

    # ---------------------------------------------------------------- produtos
    def add_product(self, name: str, price: float | None = None) -> int:
        with self._lock:
            cursor = self.db.execute(
                "insert into products(name,price,created_at) values(?,?,?)",
                (name, price, _now()),
            )
            product_id = int(cursor.lastrowid)
            self.db.commit()
        return product_id

    def list_products(self) -> list[tuple]:
        with self._lock:
            return self.db.execute(
                "select id,name,price,active from products where active=1 order by name"
            ).fetchall()

    # ------------------------------------------------------------ oportunidades
    def add_opportunity(
        self,
        lead_id: int,
        product_id: int | None = None,
        value: float | None = None,
        next_action: str = "",
    ) -> int:
        with self._lock:
            cursor = self.db.execute(
                "insert into opportunities(lead_id,product_id,value,next_action,created_at) "
                "values(?,?,?,?,?)",
                (lead_id, product_id, value, next_action, _now()),
            )
            opportunity_id = int(cursor.lastrowid)
            self.db.commit()
        return opportunity_id

    # ----------------------------------------------------------------- followups
    def add_followup(
        self,
        lead_id: int,
        due_at: str,
        task: str,
        draft: str = "",
        channel: str = "manual",
    ) -> int:
        with self._lock:
            cursor = self.db.execute(
                "insert into followups(lead_id,due_at,task,created_at,draft,status,channel) "
                "values(?,?,?,?,?,?,?)",
                (lead_id, due_at, task, _now(), draft, "draft", channel),
            )
            followup_id = int(cursor.lastrowid)
            self.db.commit()
        self.audit("followup.drafted", f"followup:{followup_id}", "ok", "status=draft; not_sent=true")
        return followup_id

    def latest_followup(self, lead_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self.db.execute(
                "select id,due_at,task,done,coalesce(draft,''),coalesce(status,'draft'),"
                "coalesce(channel,'manual'),created_at from followups "
                "where lead_id=? order by id desc limit 1",
                (lead_id,),
            ).fetchone()
        if not row:
            return None
        keys = ("id", "due_at", "task", "done", "draft", "status", "channel", "created_at")
        return dict(zip(keys, row))

    # --------------------------------------------------------------- clientes
    def add_customer(self, name: str, contact: str = "", company: str = "") -> int:
        with self._lock:
            cursor = self.db.execute(
                "insert into customers(name,contact,company,created_at) values(?,?,?,?)",
                (name, contact, company, _now()),
            )
            customer_id = int(cursor.lastrowid)
            self.db.commit()
        return customer_id

    # -------------------------------------------------------------- conversas
    def add_conversation(self, lead_id: int | None, role: str, content: str) -> int:
        with self._lock:
            cursor = self.db.execute(
                "insert into conversations(lead_id,role,content,created_at) values(?,?,?,?)",
                (lead_id, role, content, _now()),
            )
            conversation_id = int(cursor.lastrowid)
            self.db.commit()
        return conversation_id

    def list_conversations(self, lead_id: int, limit: int = 20) -> list[tuple]:
        with self._lock:
            return self.db.execute(
                "select role,content,created_at from conversations "
                "where lead_id=? order by id desc limit ?",
                (lead_id, limit),
            ).fetchall()

    # ------------------------------------------------------ estilo e conhecimento
    def add_style_sample(self, text: str, source: str = "manual") -> int:
        value = _clean_text(text)
        if not value:
            raise ValueError("A amostra de estilo está vazia.")
        with self._lock:
            cursor = self.db.execute(
                "insert into style_samples(text,source,created_at) values(?,?,?)",
                (value, source[:80] or "manual", _now()),
            )
            sample_id = int(cursor.lastrowid)
            self.db.commit()
        self.audit("style.sample_added", f"style:{sample_id}", "ok", f"source={source}; chars={len(value)}")
        return sample_id

    def list_style_samples(self, limit: int = 50) -> list[tuple]:
        limit = max(1, min(500, int(limit)))
        with self._lock:
            return self.db.execute(
                "select id,text,coalesce(source,'manual'),created_at from style_samples "
                "order by id desc limit ?",
                (limit,),
            ).fetchall()

    def style_texts(self, limit: int = 50) -> list[str]:
        return [str(row[1]) for row in self.list_style_samples(limit)]

    def clear_style_samples(self) -> int:
        with self._lock:
            count = int(self.db.execute("select count(*) from style_samples").fetchone()[0])
            self.db.execute("delete from style_samples")
            self.db.commit()
        self.audit("style.samples_cleared", "style", "ok", f"removed={count}")
        return count

    def recent_user_messages(self, limit: int = 20) -> list[str]:
        limit = max(1, min(200, int(limit)))
        with self._lock:
            rows = self.db.execute(
                "select content from messages where role='user' and length(trim(content))>0 "
                "order by id desc limit ?",
                (limit,),
            ).fetchall()
        return [str(row[0]) for row in reversed(rows)]

    def add_knowledge(self, title: str, content: str, tags: str = "") -> int:
        clean_title = _clean_detail(title, 160)
        clean_content = _clean_text(content)
        if not clean_title or not clean_content:
            raise ValueError("Informe título e conteúdo do conhecimento.")
        with self._lock:
            cursor = self.db.execute(
                "insert into knowledge(title,content,tags,active,created_at) values(?,?,?,1,?)",
                (clean_title, clean_content, _clean_detail(tags, 300), _now()),
            )
            knowledge_id = int(cursor.lastrowid)
            self.db.commit()
        self.audit("knowledge.added", f"knowledge:{knowledge_id}", "ok", f"title={clean_title}")
        return knowledge_id

    def list_knowledge(self, limit: int = 100) -> list[tuple]:
        limit = max(1, min(500, int(limit)))
        with self._lock:
            return self.db.execute(
                "select id,title,coalesce(tags,''),content,active,created_at from knowledge "
                "order by id desc limit ?",
                (limit,),
            ).fetchall()

    def knowledge_entries(self, limit: int = 100) -> list[dict]:
        return [
            {
                "id": row[0],
                "title": row[1],
                "tags": row[2],
                "content": row[3],
                "active": bool(row[4]),
                "created_at": row[5],
            }
            for row in self.list_knowledge(limit)
            if row[4]
        ]

    def delete_knowledge(self, knowledge_id: int) -> None:
        with self._lock:
            self.db.execute("update knowledge set active=0 where id=?", (knowledge_id,))
            self.db.commit()
        self.audit("knowledge.disabled", f"knowledge:{knowledge_id}", "ok", "active=false")

    # --------------------------------------------------------- consentimentos
    def add_consent(
        self,
        lead_id: int,
        channel: str = "manual",
        granted: bool = True,
        evidence: str = "",
    ) -> int:
        with self._lock:
            cursor = self.db.execute(
                "insert into consents(lead_id,channel,granted,evidence,created_at) values(?,?,?,?,?)",
                (lead_id, channel, 1 if granted else 0, _clean_detail(evidence), _now()),
            )
            consent_id = int(cursor.lastrowid)
            self.db.commit()
        self.audit(
            "consent.recorded",
            f"lead:{lead_id}",
            "ok",
            f"consent={consent_id}; channel={channel}; granted={bool(granted)}",
        )
        return consent_id

    def latest_consent(self, lead_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self.db.execute(
                "select id,channel,granted,coalesce(evidence,''),created_at from consents "
                "where lead_id=? order by id desc limit 1",
                (lead_id,),
            ).fetchone()
        if not row:
            return None
        return dict(zip(("id", "channel", "granted", "evidence", "created_at"), row))

    # ---------------------------------------------------------------- auditoria
    def audit(
        self,
        action: str,
        target: str = "",
        status: str = "ok",
        detail: str = "",
        actor: str = "system",
    ) -> int:
        with self._lock:
            cursor = self.db.execute(
                "insert into audit_events(created_at,actor,action,target,status,detail) "
                "values(?,?,?,?,?,?)",
                (_now(), actor[:80], action[:120], target[:300], status[:40], _clean_detail(detail)),
            )
            event_id = int(cursor.lastrowid)
            self.db.commit()
        return event_id

    def list_audit(self, limit: int = 50) -> list[tuple]:
        limit = max(1, min(500, int(limit)))
        with self._lock:
            return self.db.execute(
                "select created_at,actor,action,target,status,coalesce(detail,'') "
                "from audit_events order by id desc limit ?",
                (limit,),
            ).fetchall()

    # ------------------------------------------------------ aprovações humanas
    def create_pending_action(self, action: str, payload: dict, rationale: str = "") -> int:
        with self._lock:
            cursor = self.db.execute(
                "insert into pending_actions(created_at,action,payload,rationale,status) "
                "values(?,?,?,?, 'pending')",
                (
                    _now(),
                    action[:120],
                    _clean_detail(json.dumps(payload, ensure_ascii=False), 4000),
                    _clean_detail(rationale, 1000),
                ),
            )
            pending_id = int(cursor.lastrowid)
            self.db.commit()
        self.audit(
            "action.confirmation_required",
            f"pending:{pending_id}",
            "pending",
            f"action={action}; execution=disabled",
        )
        return pending_id

    def list_pending_actions(self, status: str = "pending") -> list[tuple]:
        with self._lock:
            return self.db.execute(
                "select id,created_at,action,payload,coalesce(rationale,''),status "
                "from pending_actions where status=? order by id desc",
                (status,),
            ).fetchall()

    def decide_pending_action(self, pending_id: int, approved: bool, note: str = "") -> None:
        status = "approved" if approved else "rejected"
        with self._lock:
            self.db.execute(
                "update pending_actions set status=?, decided_at=?, decision_note=? where id=?",
                (status, _now(), _clean_detail(note, 1000), pending_id),
            )
            self.db.commit()
        self.audit(
            "action.decision",
            f"pending:{pending_id}",
            status,
            "execution=disabled; human_decision_recorded=true",
        )

    # ------------------------------------------------------------------ ajustes
    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self.db.execute(
                "insert into settings(key,value,updated_at) values(?,?,?) "
                "on conflict(key) do update set value=excluded.value, updated_at=excluded.updated_at",
                (key[:120], value, _now()),
            )
            self.db.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self.db.execute("select value from settings where key=?", (key[:120],)).fetchone()
        return str(row[0]) if row else default

    # ------------------------------------------------------------------- saúde
    def counts(self) -> dict[str, int]:
        with self._lock:
            result = {}
            for table in (
                "messages",
                "leads",
                "followups",
                "conversations",
                "consents",
                "audit_events",
                "pending_actions",
                "style_samples",
                "knowledge",
            ):
                result[table] = int(self.db.execute(f"select count(*) from {table}").fetchone()[0])
        return result

    def health(self) -> bool:
        try:
            with self._lock:
                self.db.execute("select 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def close(self) -> None:
        with self._lock:
            self.db.close()

    def __enter__(self) -> "Memory":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
