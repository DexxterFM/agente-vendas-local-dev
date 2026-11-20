import hashlib
import random
import re
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

STAGES = (
    "OPENING",
    "DISCOVERY",
    "OFFER",
    "EDITION_SELECT",
    "TOKEN_SENT",
    "POST_ACTIVATION",
)

FLOW_STEPS = STAGES

RESPONSE_VARIATIONS: Dict[str, List[str]] = {
    "DISCOVERY_ASK": [
        "{greeting}! Que bom falar com você. Hoje vocês já usam algum sistema para gerenciar a clínica e as evoluções de TEA, ou ainda controlam em planilhas/papel?",
        "{greeting}! Tudo bem? Me conta uma coisa: hoje a gestão dos atendimentos e evoluções TEA aí já roda em algum software específico ou vocês usam planilhas?",
        "{greeting}! Legal falar com você. Para eu entender seu momento: vocês já utilizam algum sistema de gestão para clínica TEA hoje ou fazem o controle manual?",
        "{greeting}! Como estão os atendimentos por aí? Hoje vocês já contam com algum sistema especializado para TEA/ABA ou ainda organizam tudo manualmente?",
    ],
    "ALREADY_USE_GENERIC": [
        "Entendi! E nesse sistema atual vocês pagam mensalidade por profissional ou têm estrutura própria? Pergunto porque o ERP Clínica TEA reduz bastante esse custo.",
        "Que bom que já são informatizados! Hoje vocês têm custo recorrente por usuário/profissional nesse sistema ou é plataforma própria?",
        "Legal! E hoje vocês sentem falta de alguma rotina específica de TEA/ABA nesse sistema ou pagam caro por cada terapeuta cadastrado?",
    ],
    "OFFER_3_MONTHS": [
        "Então chegou o momento ideal de conhecer o ERP Clínica TEA! Ele organiza prontuário, evolução ABA/TEA, agenda e financeiro em um só lugar — e liberamos 3 meses totalmente gratuitos para você testar na prática. Quer experimentar?",
        "Perfeito! Temos o ERP Clínica TEA feito sob medida para atendimentos de autismo (evolução terapêutica, agenda e gestão). Estamos liberando 3 meses grátis sem compromisso. Faz sentido eu liberar um acesso para você testar?",
        "Ótimo! O ERP Clínica TEA automatiza toda a rotina clínica e financeira para equipes e terapeutas de autismo. Como condição especial, estamos liberando 3 meses gratuitos para validação. Quer que eu libere um acesso para você?",
    ],
    "ASK_EDITION": [
        "Perfeito! Para eu gerar seu acesso gratuito de 3 meses agora, seu atendimento é individual (versão Profissional) ou clínica com equipe (versão Multiprofissional)?",
        "Combinado! Só me confirma um detalhe para eu emitir seu token de 3 meses: você atende sozinho(a) (Profissional) ou é clínica com equipe multidisciplinar (Multiprofissional)?",
        "Excelente! Antes de gerar seu token de 3 meses grátis, me diz: você precisa da versão Profissional (atendimento individual) ou Multiprofissional (clínica com equipe)?",
    ],
    "POST_TOKEN_THANKS": [
        "Por nada! Qualquer dúvida na ativação ou configuração inicial, nosso time de suporte no WhatsApp está à disposição.",
        "Imagina! Assim que ativar seu token, se precisar de ajuda para importar dados ou configurar a agenda, é só chamar no suporte.",
        "Eu que agradeço! Qualquer coisa na hora de configurar o ambiente, pode nos chamar por aqui ou no WhatsApp de suporte.",
    ],
}


class SalesFlowEngine:
    """Motor de diálogo consultivo baseado em máquina de estados, variações naturais e aprendizado."""

    def __init__(self, memory_db=None, flow_studio=None, competitor_catalog=None, llm_client=None):
        self.db = memory_db
        self.flow_studio = flow_studio
        self.competitors = competitor_catalog
        self.llm = llm_client

    @staticmethod
    def _norm(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    @staticmethod
    def _time_greeting() -> str:
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "Bom dia"
        if 12 <= hour < 18:
            return "Boa tarde"
        return "Boa noite"

    def _pick_variation(self, key: str, recent_global_hashes: Optional[Set[str]] = None) -> str:
        options = RESPONSE_VARIATIONS.get(key, [])
        if not options:
            return ""
        hashes = recent_global_hashes or set()
        greeting = self._time_greeting()
        rendered = [opt.format(greeting=greeting) for opt in options]
        candidates = [
            opt for opt in rendered
            if hashlib.sha256(self._norm(opt).encode("utf-8")).hexdigest() not in hashes
        ]
        return random.choice(candidates or rendered)

    def detect_global_interruption(self, msg: str) -> Optional[Tuple[str, List[str], Optional[str]]]:
        """Camada 1: Interrupções globais que sobrepõem qualquer estágio."""
        t = self._norm(msg)

        if re.search(r"\b(n[aã]o quero|sem interesse|n[aã]o tenho interesse|pare de|n[aã]o mande mais|tirar da lista)\b", t):
            return ("OPT_OUT", ["Sem problemas! Agradeço a atenção e desejo muito sucesso nos atendimentos. Qualquer coisa no futuro, estamos por aqui."], "MARK_OPT_OUT")

        if re.search(r"\b(atendente|humano|falar com algu[eé]m|reclama[cç][aã]o|suporte urgente|erro grave|insatisfeit[oa])\b", t):
            return ("HUMAN_HANDOFF", ["Entendi! Já estou direcionando sua conversa para um de nossos especialistas humanos dar continuidade agora mesmo."], "PAUSE_BOT")

        if re.search(r"\b(boleto|pix|fatura|cobran[cç]a|pagar|pagamento|nota fiscal|cartao|cart[aã]o)\b", t):
            return ("BILLING_FLOW", [
                "Sobre questões financeiras e faturamento, não realizamos cobranças automáticas por aqui.",
                "Nossa equipe financeira valida tudo diretamente com você de forma transparente.",
                "Vou acionar o setor responsável para te atender com segurança sobre esse ponto.",
            ], None)

        if re.search(r"\b(parceria|divulga[cç][aã]o|afiliado|influenciador|collab|patroc[ií]nio)\b", t):
            return ("PARTNERSHIP", ["Que legal o interesse em parceria! Vou encaminhar seu perfil para nossa área comercial avaliar e conversar com você."], None)

        return None

    def route(self, username: str, incoming_text: str, current_stage: str = "DISCOVERY", recent_global_hashes: Optional[Set[str]] = None):
        interruption = self.detect_global_interruption(incoming_text)
        if interruption:
            intent, bubbles, action = interruption
            return {"intent": intent, "next_stage": current_stage, "bubbles": bubbles, "action": action}

        t = self._norm(incoming_text)
        greeting = self._time_greeting()
        hashes = recent_global_hashes or set()

        if current_stage == "OPENING":
            if re.search(r"\b(?:eu quero|quero|sim|s[ií]m|claro|manda|envia)\b", t):
                return {"intent": "GIFT_ACCEPTANCE", "next_stage": "EDITION_SELECT", "bubbles": [self._pick_variation("ASK_EDITION", hashes)], "action": None}
            return {"intent": "OPENING", "next_stage": "OPENING", "bubbles": ["Obrigado por seguir! Parabéns pelo trabalho da clínica! Tenho um presente para a sua equipe. Diga “eu quero” que te mando para você. 😊"], "action": None}

        if current_stage == "DISCOVERY":
            if re.search(r"\b(?:n[aã]o|ainda n[aã]o|nunca|nenhum|n[aã]o usamos|n[aã]o uso)\b", t):
                return {"intent": "NO_APP_OFFER", "next_stage": "OFFER", "bubbles": ["Então chegou o momento de conhecer algo que pode salvar muitas horas do seu dia.", "Assim sobra mais tempo para o que importa: cuidar dos seus pacientes. 😊", "Você atende em uma clínica com equipe ou em consultório individual?"], "action": None}
            if re.search(r"\b(?:j[aá]\s*uso|j[aá]\s*usamos|j[aá]\s*usei|j[aá]\s*utilizo)\b", t):
                return {"intent": "ALREADY_USE", "next_stage": "DISCOVERY", "bubbles": ["Que bom que já utiliza! Me conta: vocês ainda pagam mensalidade por esse sistema ou já possuem um app profissional próprio da empresa? 😊", "Dependendo da resposta, posso mostrar como o ERP Clínica TEA pode complementar ou substituir o que vocês usam hoje."], "action": None}
            if re.fullmatch(r"(?:sim|s[ií]m)[.! 😊]*", t.strip(), re.I):
                return {"intent": "DISCOVERY_QUALIFY", "next_stage": "DISCOVERY", "bubbles": ["Que bom! Qual app ou programa vocês usam hoje para organizar a gestão?"], "action": None}
            if re.search(r"\b(?:cl[ií]nica|equipe|multiprofissional)\b", t):
                return {"intent": "PROFILE_CLINIC", "next_stage": "OFFER", "bubbles": ["Perfeito! O ERP Clínica TEA Multiprofissional reúne agenda, prontuários e a operação da equipe em um só lugar.", "Posso enviar o link para ativar os 3 meses gratuitos?"], "action": None}
            if re.search(r"\b(?:sozinh[oa]|individual|consult[oó]rio|aut[oô]nom[oa])\b", t):
                return {"intent": "PROFILE_PRO", "next_stage": "OFFER", "bubbles": ["Perfeito! O Clínica TEA Profissional foi pensado para quem atende de forma independente e quer uma rotina organizada.", "Posso enviar o link para ativar os 3 meses gratuitos?"], "action": None}
            if re.search(r"\b(?:eu quero|quero|sim|s[ií]m|claro|manda|envia)\b", t):
                return {"intent": "GIFT_ACCEPTANCE", "next_stage": "EDITION_SELECT", "bubbles": [self._pick_variation("ASK_EDITION", hashes)], "action": None}
            return {"intent": "DISCOVERY", "next_stage": "DISCOVERY", "bubbles": [self._pick_variation("DISCOVERY_ASK", hashes)], "action": None}

        if current_stage == "OFFER":
            if re.search(r"\b(?:eu quero|quero|sim|s[ií]m|claro|manda|envia|pode)\b", t):
                return {"intent": "QUALIFY_EDITION", "next_stage": "EDITION_SELECT", "bubbles": [self._pick_variation("ASK_EDITION", hashes)], "action": None}
            return {"intent": "OFFER", "next_stage": "OFFER", "bubbles": [self._pick_variation("OFFER_3_MONTHS", hashes)], "action": None}

        if current_stage == "EDITION_SELECT":
            edition = None
            if re.search(r"\b(?:cl[ií]nica|multiprofissional|equipe)\b", t):
                edition = "clinic"
            elif re.search(r"\b(?:profissional|individual|consult[oó]rio|sozinh[oa])\b", t):
                edition = "professional"
            if edition:
                action_name = "GENERATE_TOKEN_MULTI" if edition == "clinic" else "GENERATE_TOKEN_PRO"
                return {"intent": "EDITION_SELECTED", "next_stage": "TOKEN_SENT", "bubbles": [], "action": action_name, "edition": edition}
            return {"intent": "EDITION_SELECT", "next_stage": "EDITION_SELECT", "bubbles": [self._pick_variation("ASK_EDITION", hashes)], "action": None}

        if current_stage == "TOKEN_SENT":
            if re.search(r"\b(?:ativei|ativado|consegui|instalei|deu certo|funcionou|j[aá]\s*estou usando)\b", t):
                return {"intent": "ACTIVATION_CONFIRMED", "next_stage": "POST_ACTIVATION", "bubbles": [self._pick_variation("POST_TOKEN_THANKS", hashes)], "action": None}
            if re.search(r"\b(?:obrigad[oa]|valeu|agradeço|obg)\b", t):
                return {"intent": "POST_TOKEN_THANKS", "next_stage": "TOKEN_SENT", "bubbles": [self._pick_variation("POST_TOKEN_THANKS", hashes)], "action": None}
            if re.search(r"\b(?:pre[çc]o|valor|quanto|mensalidade)\b", t):
                return {"intent": "PRICE_QUESTION", "next_stage": "TOKEN_SENT", "bubbles": ["O ERP Clínica TEA tem um período de teste gratuito de 3 meses. 😊", "É uma ativação segura: seus dados são criptografados, sem uso de cartão e sem dados bancários."], "action": None}
            return {"intent": "TOKEN_SENT", "next_stage": "TOKEN_SENT", "bubbles": ["Quando quiser ativar seu token, é só me avisar! Estou por aqui. 😊"], "action": None}

        if current_stage == "POST_ACTIVATION":
            return {"intent": "POST_ACTIVATION", "next_stage": "POST_ACTIVATION", "bubbles": [self._pick_variation("POST_TOKEN_THANKS", hashes)], "action": None}

        return {"intent": "FALLBACK", "next_stage": current_stage, "bubbles": ["Olá! Vocês já usam algum app ou programa para fazer a gestão da clínica?"], "action": None}

    def detect_stage(self, history):
        if not history:
            return "OPENING"
        texts = [str(row[1]) for row in history if len(row) > 1]
        all_text = " ".join(texts)
        if re.search(r"parab[eé]ns pela ativa[cç][aã]o|app est[aá] pronto", all_text):
            return "POST_ACTIVATION"
        if re.search(r"seu link de instala[cç][aã]o|link de ativa", all_text):
            return "TOKEN_SENT"
        if re.search(r"escolha entre", all_text):
            return "EDITION_SELECT"
        if re.search(r"3 meses gr[aá]tis|liberamos 3 meses", all_text):
            return "OFFER"
        return "DISCOVERY"

    def respond(self, username, incoming_text, history=None, recent_global_hashes=None):
        stage = self.detect_stage(history or [])
        result = self.route(username, incoming_text, stage, recent_global_hashes)
        return result
