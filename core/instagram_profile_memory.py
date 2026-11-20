"""Banco de memória dedicado a perfis do Instagram e ao fluxo de diálogo.

Cada mensagem já enviada a um perfil é gravada como um **passo do fluxo**
(``flow_step``) com o hash do texto normalizado. Antes de qualquer envio o
agente compara a mensagem proposta com o que já foi postado para aquele perfil.
Isso impede reenvios que podem gerar denúncia por spam, mesmo após reiniciar o
worker ou reconstruir a conversa na tela.

Diferenças em relação a ``ProfileMemory`` (settings genéricas):
- tabelas próprias com índice e chave única por (perfil, hash);
- cada balão é um passo nomeado do fluxo (intro, pergunta_app, objeção, link...);
- consulta explícita de "o que já foi dito" para decidir se envia ou não.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

# Passos canônicos do fluxo de diálogo. Usados como rótulos estáveis no banco.
FLOW_STEPS = (
    "intro",
    "welcome_question",
    "prize_choice",
    "install_link",
    "install_validity",
    "install_security",
    "install_support",
    "activation_congratulations",
    "ask_app_usage",
    "existing_app_objection",
    "no_app_offer",
    "compare_offer",
    "ask_profile_type",
    "proposal",
    "payment_concern",
    "human_handoff",
    "closing",
    "reply",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_username(username) -> str:
    return str(username or "").strip().lstrip("@").lower()


def _normalize(text) -> str:
    import unicodedata
    raw = " ".join(str(text or "").split())
    return unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii").casefold()


def _hash(text) -> str:
    import hashlib
    return hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()


class InstagramProfileMemory:
    """Leitura/escrita das tabelas dedicadas de perfil e fluxo."""

    def __init__(self, memory):
        self.memory = memory

    # ---------------------------------------------------------------- perfil
    def ensure_profile(self, username, *, kind="", segment="", specialties=None,
                       thread_id="") -> int:
        username = _clean_username(username)
        if not username:
            raise ValueError("Usuário Instagram inválido")
        with self.memory._lock:
            row = self.memory.db.execute(
                "select id from instagram_profiles where username=?", (username,)
            ).fetchone()
            now = _now()
            if row:
                profile_id = int(row[0])
                updates = ["updated_at=?"]
                params = [now]
                if kind:
                    updates.append("kind=?"); params.append(str(kind)[:40])
                if segment:
                    updates.append("segment=?"); params.append(str(segment)[:40])
                if thread_id:
                    updates.append("thread_id=?"); params.append(str(thread_id)[:120])
                if specialties is not None:
                    updates.append("specialties=?")
                    params.append(json.dumps(sorted(set(specialties)), ensure_ascii=False))
                params.append(profile_id)
                self.memory.db.execute(
                    f"update instagram_profiles set {','.join(updates)} where id=?", params
                )
            else:
                cursor = self.memory.db.execute(
                    "insert into instagram_profiles(username,kind,segment,specialties,thread_id,created_at,updated_at) "
                    "values(?,?,?,?,?,?,?)",
                    (username, str(kind)[:40], str(segment)[:40],
                     json.dumps(sorted(set(specialties or [])), ensure_ascii=False),
                     str(thread_id)[:120], now, now),
                )
                profile_id = int(cursor.lastrowid)
            self.memory.db.commit()
            return profile_id

    def get_profile(self, username) -> dict:
        username = _clean_username(username)
        if not username:
            return {}
        row = self.memory.db.execute(
            "select id,username,kind,segment,specialties,thread_id,stage,created_at,updated_at "
            "from instagram_profiles where username=?", (username,)
        ).fetchone()
        if not row:
            return {}
        keys = ("id", "username", "kind", "segment", "specialties", "thread_id", "stage",
                "created_at", "updated_at")
        data = dict(zip(keys, row))
        try:
            data["specialties"] = json.loads(data.get("specialties") or "[]")
        except (TypeError, ValueError):
            data["specialties"] = []
        return data

    def set_stage(self, username, stage) -> None:
        username = _clean_username(username)
        with self.memory._lock:
            self.memory.db.execute(
                "update instagram_profiles set stage=?,updated_at=? where username=?",
                (str(stage)[:40], _now(), username),
            )
            self.memory.db.commit()

    # ------------------------------------------------------------- mensagens
    def record_sent(self, username, text, *, flow_step="reply", direction="outgoing",
                    thread_id="", sender_type="agent") -> bool:
        """Grava uma mensagem enviada como passo do fluxo.

        Retorna True se é uma mensagem nova; False se já estava registrada.
        sender_type: 'agent' (bot) ou 'operator' (humano).
        """
        username = _clean_username(username)
        if not username or not text:
            return False
        profile_id = self.ensure_profile(username, thread_id=thread_id)
        digest = _hash(text)
        with self.memory._lock:
            existing = self.memory.db.execute(
                "select id from instagram_profile_messages where profile_id=? and hash=?",
                (profile_id, digest),
            ).fetchone()
            if existing:
                return False
            self.memory.db.execute(
                "insert into instagram_profile_messages(profile_id,flow_step,hash,text,direction,sender_type,thread_id,created_at) "
                "values(?,?,?,?,?,?,?,?)",
                (profile_id, str(flow_step)[:40], digest, str(text)[:3500],
                 str(direction)[:12], str(sender_type)[:12], str(thread_id)[:120], _now()),
            )
            self.memory.db.commit()
        return True

    def record_message(self, username, text, *, flow_step="reply", direction="outgoing",
                       sender_type="agent", thread_id="") -> bool:
        """Alias de record_sent com suporte explícito a sender_type."""
        return self.record_sent(
            username, text, flow_step=flow_step, direction=direction,
            thread_id=thread_id, sender_type=sender_type,
        )

    def get_stage(self, username) -> str:
        username = _clean_username(username)
        if not username:
            return "OPENING"
        row = self.memory.db.execute(
            "select current_stage from instagram_profiles where username=?", (username,)
        ).fetchone()
        if not row or not row[0]:
            return "OPENING"
        return str(row[0])

    def set_stage(self, username, stage) -> None:
        username = _clean_username(username)
        if not username:
            return
        with self.memory._lock:
            self.ensure_profile(username)
            self.memory.db.execute(
                "update instagram_profiles set current_stage=?, updated_at=? where username=?",
                (str(stage)[:40], _now(), username),
            )
            self.memory.db.commit()

    def get_recent_global_hashes(self, limit=20) -> set:
        """Hashes de mensagens recentes (qualquer perfil) para evitar repetir variação."""
        rows = self.memory.db.execute(
            "select hash from instagram_profile_messages order by id desc limit ?",
            (int(limit),),
        ).fetchall()
        return {str(r[0]) for r in rows if r[0]}

    def already_sent(self, username, text) -> bool:
        username = _clean_username(username)
        row = self.memory.db.execute(
            "select m.id from instagram_profile_messages m "
            "join instagram_profiles p on p.id=m.profile_id "
            "where p.username=? and m.hash=?",
            (username, _hash(text)),
        ).fetchone()
        return row is not None

    def sent_messages(self, username, limit=100) -> list[dict]:
        """Histórico de mensagens já postadas para o perfil, em ordem cronológica."""
        username = _clean_username(username)
        rows = self.memory.db.execute(
            "select m.flow_step,m.hash,m.text,m.direction,m.thread_id,m.created_at "
            "from instagram_profile_messages m "
            "join instagram_profiles p on p.id=m.profile_id "
            "where p.username=? order by m.id asc limit ?",
            (username, int(limit)),
        ).fetchall()
        return [
            {"flow_step": r[0], "hash": r[1], "text": r[2], "direction": r[3],
             "thread_id": r[4], "created_at": r[5]}
            for r in rows
        ]

    def last_step(self, username) -> str:
        username = _clean_username(username)
        row = self.memory.db.execute(
            "select m.flow_step from instagram_profile_messages m "
            "join instagram_profiles p on p.id=m.profile_id "
            "where p.username=? and m.direction='outgoing' order by m.id desc limit 1",
            (username,),
        ).fetchone()
        return str(row[0]) if row else ""

    def steps_taken(self, username) -> list[str]:
        username = _clean_username(username)
        rows = self.memory.db.execute(
            "select distinct m.flow_step from instagram_profile_messages m "
            "join instagram_profiles p on p.id=m.profile_id "
            "where p.username=? and m.direction='outgoing' order by m.id asc",
            (username,),
        ).fetchall()
        return [str(r[0]) for r in rows]

    def can_send(self, username, text) -> tuple[bool, str]:
        """Decide se a mensagem pode ser enviada a este perfil.

        Regras:
        1. texto vazio nunca é enviado;
        2. hash já registrado para o perfil => bloqueia (nunca reenvia);
        3. caso contrário, permite.
        """
        if not _normalize(text):
            return False, "empty"
        if self.already_sent(username, text):
            return False, "already-sent-to-profile"
        return True, ""


def infer_flow_step(text) -> str:
    """Infere o passo do fluxo a partir do texto da mensagem enviada."""
    import re
    value = _normalize(text)
    rules = (
        ("install_link", r"seu link de instalacao|link de ativacao"),
        ("install_validity", r"valido por 3 dias|validade do link|perde o premio"),
        ("install_security", r"criptografad|sem cartao|sem dados bancarios|ativacao segura"),
        ("install_support", r"whatsapp|assintencia|51 8054"),
        ("activation_congratulations", r"parabens pela ativacao|app esta pronto"),
        ("prize_choice", r"escolha entre|parabens voce ganhou|3 meses gratis"),
        ("existing_app_objection", r"paga mensalidade|app profissional proprio"),
        ("no_app_offer", r"salvar muitas horas|consultorio individual"),
        ("compare_offer", r"comparar rapidamente|posso comparar"),
        ("ask_profile_type", r"clinica com equipe|consultorio individual"),
        ("payment_concern", r"cobranca automatica|nao gera cobranca"),
        ("human_handoff", r"especialista da nossa equipe|atendente"),
        ("closing", r"fica com deus|grande abra|ate logo"),
        ("welcome_question", r"ja possui algum app|ja utiliza algum app|qual app ou programa"),
        ("intro", r"obrigado por seguir|vi o trabalho|muito legal o trabalho|tenho um presente"),
    )
    for step, pattern in rules:
        if re.search(pattern, value):
            return step
    return "reply"


def profile_flow_memory(memory) -> InstagramProfileMemory:
    return InstagramProfileMemory(memory)
