"""Gera o fluxograma de ramificações dos diálogos do agente em SVG.

Desenha um grafo de decisões real: cada nó é uma fala/etapa do agente e cada
aresta é uma resposta possível do cliente que ramifica o caminho. O arquivo
SVG resultante pode ser convertido para PNG com Chrome headless.
"""
from __future__ import annotations

from pathlib import Path

# Paleta
BG = "#07111f"
TEAL = "#16d8d2"
TEAL_L = "#6effef"
PURPLE = "#a88aff"
AMBER = "#ffb52d"
GREEN = "#3ee48c"
RED = "#ff7373"
MUTED = "#8b9bb0"
CARD = "#0c1a2a"
CARD_INTER = "#120e22"
LINE = "#2b4a68"
WHITE = "#eff6ff"

# Nós: id -> (x, y, largura, altura, titulo, subtipo/linhas, cor_borda)
NODES: dict[str, tuple] = {
    "start":   (40, 400, 200, 92, "1 · ABERTURA", ["Presente · aguarda", '"eu quero"'], TEAL),
    "disc":    (330, 385, 230, 122, "2 · DESCOBERTA", ["Usa app? Clínica ou", "profissional?"], TEAL),
    "offer":   (700, 385, 210, 110, "3 · OFERTA", ["3 meses grátis"], TEAL),
    "edition": (1040, 385, 220, 110, "4 · ESCOLHA", ["Profissional ou", "Multiprofissional?"], TEAL),
    "token_pro": (1400, 230, 200, 96, "5a · TOKEN PRO", ["Link + código (Profissional)"], GREEN),
    "token_multi": (1400, 530, 205, 96, "5b · TOKEN MULTI", ["Link + código (Clínica)"], GREEN),
    "post":    (1725, 385, 190, 100, "6 · PÓS-ATIVAÇÃO", ["Suporte + WhatsApp"], GREEN),
}

# Arestas: (de, para, rótulo, cor, curva/ponto de controle em y)
EDGES = [
    ("start", "disc", "eu quero / sim", AMBER, 0),
    ("disc", "offer", "não uso / clínica / individual", AMBER, -6),
    ("offer", "edition", "quero testar", AMBER, 0),
    ("edition", "token_pro", "profissional / sozinho", PURPLE, -70),
    ("edition", "token_multi", "clínica / equipe", PURPLE, 70),
    ("token_pro", "post", "ativei", GREEN, -60),
    ("token_multi", "post", "ativei", GREEN, 60),
]

# Auto-aresta (já uso -> volta para descoberta) e ramificação extra
SELF_LOOP = ("disc", "já uso → pergunta custo/benefício", PURPLE)

W, H = 1980, 1020

def esc(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def node_svg() -> str:
    out = []
    for nid, (x, y, w, h, title, lines, color) in NODES.items():
        cx = x + w / 2
        # caixa
        out.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" '
            f'fill="{CARD}" stroke="{color}" stroke-width="2"/>'
        )
        out.append(
            f'<text x="{cx}" y="{y+26}" text-anchor="middle" fill="{TEAL_L}" '
            f'font-family="Segoe UI" font-size="13" font-weight="700">{esc(title)}</text>'
        )
        for i, line in enumerate(lines):
            out.append(
                f'<text x="{cx}" y="{y+47+i*16}" text-anchor="middle" fill="#c9d8e7" '
                f'font-family="Segoe UI" font-size="11">{esc(line)}</text>'
            )
    return "\n".join(out)

MARKER = {AMBER: "arrow", PURPLE: "arrowp", GREEN: "arrowg", TEAL: "arrowt"}

def edge_svg() -> str:
    out = []
    for src, dst, label, color, bend in EDGES:
        sx, sy, sw, sh, *_ = NODES[src]
        dx, dy, dw, dh, *_ = NODES[dst]
        x1, y1 = sx + sw, sy + sh / 2
        x2, y2 = dx, dy + dh / 2
        my = (y1 + y2) / 2 + bend
        # curva bezier suave
        path = f'M {x1} {y1} C {(x1+x2)/2} {y1}, {(x1+x2)/2} {y2}, {x2} {y2}'
        marker = MARKER.get(color, "arrow")
        out.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2" marker-end="url(#{marker})"/>')
        lx = (x1 + x2) / 2
        ly = my - 8
        # rótulos longos são quebrados em duas linhas para não invadir as caixas
        parts = label.split(" / ")
        if len(parts) > 2:
            parts = [label[:len(label)//2], label[len(label)//2:]]
        for i, part in enumerate(parts):
            out.append(
                f'<text x="{lx}" y="{ly - i*12}" text-anchor="middle" fill="{color}" '
                f'font-family="Segoe UI" font-size="10">{esc(part)}</text>'
            )
    # auto-aresta "já uso" acima do nó descoberta
    x, y, w, h, *_ = NODES["disc"]
    out.append(
        f'<path d="M {x+40} {y} C {x+20} {y-55}, {x+w-20} {y-55}, {x+w-40} {y}" '
        f'fill="none" stroke="{PURPLE}" stroke-width="2" stroke-dasharray="5,4" marker-end="url(#arrowp)"/>'
    )
    out.append(
        f'<text x="{x+w/2}" y="{y-62}" text-anchor="middle" fill="{PURPLE}" '
        f'font-family="Segoe UI" font-size="10.5">{esc(SELF_LOOP[1])}</text>'
    )
    return "\n".join(out)

def interruptions_svg() -> str:
    boxes = [
        ("OPT_OUT", "Não quero / parar", "sem problemas, encerra"),
        ("HUMAN_HANDOFF", "Falar com humano", "pausa o bot"),
        ("BILLING_FLOW", "Financeiro / cobrança", "sem cobrança automática"),
        ("PARTNERSHIP", "Parceria / divulgação", "encaminha à área comercial"),
    ]
    out = [f'<text x="40" y="750" fill="{WHITE}" font-family="Segoe UI" font-size="15" font-weight="700">⚡ INTERRUPÇÕES GLOBAIS</text>',
           f'<text x="300" y="750" fill="{MUTED}" font-family="Segoe UI" font-size="11">ocorrem em qualquer etapa e sobrepõem o roteiro</text>']
    widths = [400, 400, 400, 400]
    xs = [40, 460, 890, 1320]
    ys = [775, 885]
    for i, (code, title, desc) in enumerate(boxes):
        x = xs[i % 2] if i < 2 else xs[i - 2] + (430 if i == 2 else 0)
        y = ys[i % 2]
        # posições manuais para 2x2
        positions = [(40, 775), (520, 775), (1000, 775), (1480, 775)]
        x, y = positions[i]
        out.append(f'<rect x="{x}" y="{y}" width="400" height="92" rx="12" fill="{CARD_INTER}" stroke="{PURPLE}" stroke-width="1.5"/>')
        out.append(f'<text x="{x+16}" y="{y+25}" fill="{WHITE}" font-family="Segoe UI" font-size="12" font-weight="700">{esc(title)}</text>')
        out.append(f'<text x="{x+16}" y="{y+45}" fill="{PURPLE}" font-family="monospace" font-size="10">{esc(code)}</text>')
        out.append(f'<text x="{x+16}" y="{y+66}" fill="#cfdce8" font-family="Segoe UI" font-size="10.5">{esc(desc)}</text>')
    return "\n".join(out)

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="{AMBER}"/>
  </marker>
  <marker id="arrowp" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="{PURPLE}"/>
  </marker>
  <marker id="arrowg" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="{GREEN}"/>
  </marker>
  <marker id="arrowt" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="{TEAL}"/>
  </marker>
  <radialGradient id="bg" cx="75%" cy="-10%" r="80%">
    <stop offset="0%" stop-color="#12324a"/><stop offset="100%" stop-color="{BG}"/>
  </radialGradient>
</defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<text x="40" y="58" fill="{WHITE}" font-family="Segoe UI" font-size="27" font-weight="700">Mapa do Fluxo de <tspan fill="{TEAL}">Diálogo</tspan> · ramificações</text>
<text x="40" y="82" fill="{MUTED}" font-family="Segoe UI" font-size="12">Cada seta é uma resposta do cliente que ramifica o caminho do agente</text>
{edge_svg()}
{node_svg()}
{interruptions_svg()}
<text x="40" y="1000" fill="#5f7f96" font-family="Segoe UI" font-size="10">Agente de Vendas Local · derivado de SalesFlowEngine + FlowStudio · 21/11/2026</text>
</svg>'''

out = Path(__file__).parent / "fluxograma_ramificacoes.svg"
out.write_text(svg, encoding="utf-8")
print(f"SVG gerado: {out} ({out.stat().st_size} bytes)")
