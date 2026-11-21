"""Mapa completo do fluxo esperado da interação do agente.

Reúne em uma única estrutura os estágios, as intenções que fazem o diálogo
avançar, as respostas/variações de cada etapa e as interrupções globais. O
objetivo é dar ao operador uma visão completa do roteiro — o que o agente
deve dizer, em que ordem e o que o cliente precisa responder para avançar.

Toda a leitura é determinística e derivada do código real do agente
(`sales_flow_engine`, `flow_studio` e `desktop_rpc`), sem duplicar regras de
resposta. A biblioteca editável (flow_studio) é anexada para mostrar onde o
texto de cada balão pode ser ajustado.
"""
from __future__ import annotations

from typing import Any


# Cada estágio descreve o objetivo, as respostas possíveis e as transições.
# As transições usam o mesmo vocabulário de intenções de SalesFlowEngine.route.
STAGE_FLOW: list[dict[str, Any]] = [
    {
        "id": "OPENING",
        "order": 1,
        "label": "Abertura / Presente",
        "objective": "Agradecer o seguir e despertar interesse com um presente, sem revelar a oferta antes do interesse.",
        "agent_bubbles": [
            "Obrigado por seguir! Parabéns pelo trabalho da clínica! Tenho um presente para a sua equipe. Diga “eu quero” que te mando para você. 😊",
        ],
        "template_ids": ["intro-follow-clinic", "intro-follow-professional", "intro-follow-community"],
        "waits_for": "O cliente manifestar interesse (“eu quero”, “sim”, “quero”).",
        "transitions": [
            {"intent": "GIFT_ACCEPTANCE", "trigger": "eu quero | quero | sim | claro | manda | envia", "next": "EDITION_SELECT"},
        ],
    },
    {
        "id": "DISCOVERY",
        "order": 2,
        "label": "Descoberta / Qualificação",
        "objective": "Entender se a pessoa usa algum sistema, se é clínica com equipe ou atendimento individual.",
        "agent_bubbles": [
            "Você merece! Me conta: já possui algum app para a gestão da sua clínica? 😊",
            "Tudo bem! Por acaso já utiliza algum app ou programa para administrar sua clínica? Se já usa, qual?",
        ],
        "template_ids": ["welcome-app", "qualified-greeting", "no-app", "existing-app", "free-app-offer-1", "free-app-offer-2"],
        "waits_for": "O cliente dizer se usa app e se atende sozinho ou em equipe.",
        "transitions": [
            {"intent": "NO_APP_OFFER", "trigger": "não | ainda não | nunca | não usamos", "next": "OFFER"},
            {"intent": "ALREADY_USE", "trigger": "já uso | já usamos | já utilizo", "next": "DISCOVERY"},
            {"intent": "PROFILE_CLINIC", "trigger": "clínica | equipe | multiprofissional", "next": "OFFER"},
            {"intent": "PROFILE_PRO", "trigger": "sozinho | individual | consultório | autônomo", "next": "OFFER"},
            {"intent": "DISCOVERY_QUALIFY", "trigger": "sim", "next": "DISCOVERY"},
        ],
    },
    {
        "id": "OFFER",
        "order": 3,
        "label": "Apresentação / Oferta",
        "objective": "Apresentar o ERP Clínica TEA e os 3 meses grátis, conduzindo à escolha da edição.",
        "agent_bubbles": [
            "Então chegou o momento de conhecer algo que pode salvar muitas horas do seu dia.",
            "Assim sobra mais tempo para o que importa: cuidar dos seus pacientes. 😊",
            "Você atende em uma clínica com equipe ou em consultório individual?",
        ],
        "template_ids": ["no-app", "three-months"],
        "waits_for": "O cliente confirmar interesse em testar.",
        "transitions": [
            {"intent": "QUALIFY_EDITION", "trigger": "eu quero | quero | sim | pode | manda", "next": "EDITION_SELECT"},
        ],
    },
    {
        "id": "EDITION_SELECT",
        "order": 4,
        "label": "Escolha da Edição",
        "objective": "Confirmar se é versão Profissional (individual) ou Multiprofissional (clínica com equipe).",
        "agent_bubbles": [
            "Perfeito! Para eu gerar seu acesso gratuito de 3 meses agora, seu atendimento é individual (versão Profissional) ou clínica com equipe (versão Multiprofissional)?",
        ],
        "template_ids": ["prize-choice"],
        "waits_for": "O cliente escolher a edição.",
        "transitions": [
            {"intent": "EDITION_SELECTED · clinic", "trigger": "clínica | multiprofissional | equipe", "next": "TOKEN_SENT", "action": "Gerar token Multiprofissional"},
            {"intent": "EDITION_SELECTED · professional", "trigger": "profissional | individual | consultório | sozinho", "next": "TOKEN_SENT", "action": "Gerar token Profissional"},
        ],
    },
    {
        "id": "TOKEN_SENT",
        "order": 5,
        "label": "Link + Token + Avisos",
        "objective": "Entregar o link de instalação, o código de ativação e os avisos em bolhas separadas.",
        "agent_bubbles": [
            "Perfeito! A versão escolhida é a ideal para você.",
            "Seu link de instalação: https://erpclinicatea.com/login/admin?...",
            "Seu código de ativação: ERPDEMO-XXXXXXXX-xxxx-xxxx",
            "Aviso esse link é valido por 3 dias. Caso não seja ativado voce perde o premios 😢",
            "Essa é uma tivação segura seus dados saõ criptografados ... Sem uso de cartão.",
            "A intalação pode receber suporte para duvidas ... whatsapp assintencia 51 8054-2244",
        ],
        "template_ids": ["install-validity", "install-security", "install-support"],
        "waits_for": "O cliente ativar o token ou tirar dúvidas.",
        "transitions": [
            {"intent": "ACTIVATION_CONFIRMED", "trigger": "ativei | ativado | consegui | instalei | funcionou", "next": "POST_ACTIVATION"},
            {"intent": "POST_TOKEN_THANKS", "trigger": "obrigado | valeu | agradeço", "next": "TOKEN_SENT"},
            {"intent": "PRICE_QUESTION", "trigger": "preço | valor | quanto | mensalidade", "next": "TOKEN_SENT"},
        ],
    },
    {
        "id": "POST_ACTIVATION",
        "order": 6,
        "label": "Pós-ativação",
        "objective": "Agradecer e manter o suporte disponível após a ativação.",
        "agent_bubbles": [
            "Parabéns pela ativação! Seu app está pronto para uso. Se tiver dúvidas, entre em contato pelo WhatsApp de assistência: 51 8054-2244.",
        ],
        "template_ids": ["install-activation-congratulations"],
        "waits_for": "Novas dúvidas ou encerramento.",
        "transitions": [],
    },
]

INTERRUPTIONS: list[dict[str, Any]] = [
    {
        "intent": "OPT_OUT",
        "label": "Não tenho interesse / parar",
        "trigger": "não quero | sem interesse | pare de | não mande mais | tirar da lista",
        "agent_bubbles": ["Sem problemas! Agradeço a atenção e desejo muito sucesso nos atendimentos."],
        "action": "Marcar opt-out",
    },
    {
        "intent": "HUMAN_HANDOFF",
        "label": "Falar com humano / reclamação",
        "trigger": "atendente | humano | falar com alguém | reclamação | suporte urgente",
        "agent_bubbles": ["Entendi! Já estou direcionando sua conversa para um especialista humano."],
        "action": "Pausar bot",
    },
    {
        "intent": "BILLING_FLOW",
        "label": "Financeiro / cobrança",
        "trigger": "boleto | pix | fatura | cobrança | pagar | cartão",
        "agent_bubbles": [
            "Sobre questões financeiras, não realizamos cobranças automáticas por aqui.",
            "Nossa equipe financeira valida tudo diretamente com você.",
        ],
        "action": None,
    },
    {
        "intent": "PARTNERSHIP",
        "label": "Parceria / divulgação",
        "trigger": "parceria | divulgação | afiliado | influenciador | patrocínio",
        "agent_bubbles": ["Que legal o interesse em parceria! Vou encaminhar seu perfil para nossa área comercial."],
        "action": None,
    },
]


def build_flow_map(templates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Monta o mapa completo, anexando o estado editável de cada balão."""
    by_id = {str(t.get("id") or ""): t for t in (templates or []) if isinstance(t, dict)}
    stages = []
    for stage in STAGE_FLOW:
        item = dict(stage)
        item["editable_bubbles"] = [
            {
                "id": tid,
                "text": by_id.get(tid, {}).get("response", ""),
                "question": by_id.get(tid, {}).get("question", ""),
            }
            for tid in stage["template_ids"]
            if tid in by_id
        ]
        stages.append(item)
    return {
        "version": 1,
        "stages": sorted(stages, key=lambda s: s["order"]),
        "interruptions": INTERRUPTIONS,
        "summary": {
            "total_stages": len(STAGE_FLOW),
            "total_transitions": sum(len(s["transitions"]) for s in STAGE_FLOW),
            "total_interruptions": len(INTERRUPTIONS),
        },
    }
