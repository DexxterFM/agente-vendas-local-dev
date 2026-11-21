# CONTEXTO DO PROJETO — Agente de Vendas Local (ERP Clínica TEA)

## O que é
Agente de vendas autônomo para Instagram, que prospecta clínicas e profissionais de
autismo/TEA, envia DMs, responde automaticamente e entrega tokens de demonstração
de 3 meses do ERP Clínica TEA (multiprofissional e profissional). Roda em VPS
(Linux/AlmaLinux) com Chromium interno controlado por CDP.

## Estrutura principal
```
sales_agent_unified/
├── core/                          # Núcleo compartilhado (desktop + worker)
│   ├── desktop_rpc.py             # RPC do painel: draft, browserScreenCycle, tokens, flows
│   ├── memory.py                  # SQLite: leads, conversations, settings, audit
│   ├── profile_memory.py          # Cadastro persistente de perfis prospectados (settings)
│   ├── instagram_profile_memory.py # Banco dedicado: instagram_profiles + instagram_profile_messages
│   ├── conversation_context.py    # can_send(): anti-repetição por contexto/histórico
│   ├── sales_flow_engine.py       # Motor de diálogo: máquina de estados + variações naturais
│   ├── sales_intelligence.py      # Contexto RAG e passos do fluxo de vendas
│   ├── flow_studio.py             # Biblioteca de fluxos editáveis (templates + learn_from_operator)
│   ├── activation_token.py        # Tokens de ativação (single-use, 30 dias)
│   ├── erp_token_client.py        # Geração de tokens no ERP (professional/multiprofissional)
│   ├── job_scheduler.py           # Fila alternada sales/prospecting + HumanRateLimiter
│   └── config.py                  # Configuração (db_path, ollama, etc.)
├── scripts/vps/
│   ├── internal_browser.py        # Cliente CDP do Chromium (teclado, snapshot, tabs, humanização)
│   ├── internal_browser_agent.py  # Loop do agente: cycle(), _process_thread, _prospecting_cycle
│   └── sales_agent_worker.py      # Worker systemd
├── desktop/
│   └── main.cjs                   # Electron: túneis SSH, painel, whitelist RPC
├── frontend/
│   ├── index.html                 # Painel HTML
│   └── runtime.js                 # Lógica do painel (tokens, leads, conversas)
├── tests/                         # 276 testes (unittest)
└── OPERACAO.md                    # Guia operacional
```

## VPS
- Host: erpclinicatea-vps (SSH root)
- App: /opt/agente-vendas-local/app (symlink → release-20261117-browser-login)
- DB: /var/lib/agente-vendas-local/sales_agent.sqlite3 (SALES_AGENT_DATA_DIR)
- Worker: agente-vendas-worker.service
- RPC: agente-vendas-control.service (porta 8787)
- Browser: agente-vendas-internal-browser.service (Chromium, porta 9222)
- Navegador usa internet DIRETA da VPS (sem proxy SOCKS do PC)

## Fluxos de diálogo (draft em desktop_rpc.py)
Ordem de prioridade:
1. Não quero/sem interesse → despedida
2. Atendente/humano → direciona para especialista
3. Reclamação → direciona para especialista
4. Cobrança/pagamento → roteiro de 3 balões (sem cobrança automática)
5. App gratuito → oferta de 3 meses grátis
6. "Sim" (confirma uso de app) → "Que bom! Qual app vocês usam?"
7. "Já uso/já usei" → objeção: "pagam mensalidade ou têm app próprio?" + comparativo
8. "Não/ainda não/nunca" → no-app: "Então chegou o momento de conhecer..."
9. "Eu quero" → link + token 3 meses + 3 avisos (validade, segurança, suporte)
10. Escolha de versão (multiprofissional/profissional) → link + token
11. Confirmação de ativação → pós-ativação + WhatsApp
12. Pergunta de preço → condições do teste gratuito
13. Parceria → acolhimento próprio
14. Agradecimento → "Você merece! Já possui algum app?"
15. Saudação qualificada → retoma descoberta
16. FlowStudio.match (templates customizados + aprendizado do operador)
17. CompetitorCatalog (comparativo documentado)
18. Fallback genérico / LLM local

## Anti-repetição (memória por perfil)
- Tabela `instagram_profiles`: um registro por username
- Tabela `instagram_profile_messages`: cada mensagem enviada = passo do fluxo (hash normalizado, chave única por perfil+hash)
- `can_send()` (conversation_context.py): bloqueia se hash já existe no banco ou na tela, ou se é mensagem de abertura em conversa já iniciada
- `ProfileMemory` (settings): cadastro antigo, ainda usado como fallback
- `campaignMessageGuard`: bloqueia reenvio de abertura para perfil já contatado
- `_find_lead_by_username`: busca centralizada de lead por username, priorizando leads com mais histórico
- `get_recent_global_hashes()`: evita repetir a mesma variação de texto entre leads seguidos

## Regras de não-disparo
- Agente só responde com evidência real de interação (bolinha vermelha, evento de mensagem nova, conversa aberta com fala incoming nova)
- NÃO abre conversas antigas a cada ciclo (fallback "recent-scan" removido)
- NÃO repete mensagens já enviadas (hash + banco dedicado por perfil)
- NÃO envia mensagens que não se encaixam no contexto

## Pontos de envio (4)
1. Prospecção (abertura) — perfil novo no feed, 1x por perfil
2. Resposta de DM — quando cliente envia mensagem nova
3. Novo seguidor (notificação) — "seguir de volta" na central
4. Comentário — 1 por post na prospecção

## Tokens de ativação
- Formato: `ERPDEMO-XXXXXXXX-XXXX`
- Single-use, 30 dias de validade local, 3 meses no ERP
- Geração via `POST /api/internal/demo-token` (X-Agent-Token)
- Suporta edições: professional (port 13201) e multiprofissional (port 3000)
- Lista no painel: verde=ativado, vermelho=não usado, badge de edição, datas

## Teclado de acessibilidade
- CDP `Input.dispatchKeyEvent` com `keyDown` + `keyUp` (text/unmodifiedText no keyDown)
- Sem `Input.insertText`, clipboard, `Runtime.evaluate`, pyautogui, xdotool
- Envio via Enter, clique apenas para focar

## Máquina de estados (sales_flow_engine.py)
- Estados: OPENING → DISCOVERY → OFFER → EDITION_SELECT → TOKEN_SENT → POST_ACTIVATION
- `detect_stage(history)` infere o estado a partir do histórico
- `route(username, text, stage)` retorna intent, next_stage, bubbles, action
- Variações naturais via `RESPONSE_VARIATIONS` com `_pick_variation` (evita repetição global)
- Interrupções globais: OPT_OUT, HUMAN_HANDOFF, BILLING_FLOW (3 balões), PARTNERSHIP

## HumanRateLimiter (job_scheduler.py)
- Cotas por hora/dia e intervalos mínimos para follow, prospect_dm, comment, dm_reply
- Active hours para prospect_dm (8-20h)
- Integrado em _prospecting_cycle e _process_thread

## Fechamento de abas auxiliares
- `close_auxiliary_tabs()` fecha abas extras (perfis, meta.com/about) preservando aba de trabalho e verificação
- Chamado no início de cada ciclo do worker

## Blindagem CDP (humanização)
- `ensure_single_tab_and_viewport()` — fecha abas extras, trava viewport 1280x800
- `human_click()` — trajetória com jitter + mouseMoved
- `human_type_text()` — cadência gaussiana + pausa em pontuação
- Sem `Page.navigate` para perfis/DMs — tudo via lupa + teclado + cliques

## Aprendizado com operador (flow_studio.py)
- `learn_from_operator(trigger_text, response_text, stage)` — persiste pares aprendidos
- `_tokenize()` + `_jaccard_similarity()` — matching por similaridade (>= 0.72)
- `match()` testa templates explícitos primeiro, depois pares aprendidos

## Como rodar testes
```bash
cd C:\Users\denis\Documents\opencode\sales_agent_unified
python -m unittest discover -s tests
```
276 testes, todos devem passar.

## Deploy
- VPS: `scp` dos arquivos modificados → `python3 -m py_compile` → `systemctl restart`
- Local: rebuild `app.asar` via `@electron/asar` → instalar em SalesAgentLocal + SalesAgentRemoteControl → reabrir atalho
- Commit com mensagem descritiva

## Comandos úteis na VPS
```bash
# Status
systemctl is-active agente-vendas-worker agente-vendas-control agente-vendas-internal-browser
# Logs
journalctl -u agente-vendas-worker -n 20 --no-pager
# RPC
python3 -c "import json,urllib.request; d=json.dumps({'command':'agentStatus','args':{}}).encode(); r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8787/api/rpc',data=d,headers={'Content-Type':'application/json'})); print(r.read().decode())"
# Garantir navegador sem proxy
bash /opt/agente-vendas-local/app/scripts/vps/ensure_browser_no_proxy.sh
```

## Arquivos-chave para trabalhar
- `core/desktop_rpc.py` — toda a lógica de resposta (draft, browserScreenCycle, tokens, flows)
- `core/flow_studio.py` — templates de resposta editáveis + learn_from_operator
- `core/instagram_profile_memory.py` — banco dedicado de perfis e mensagens
- `core/conversation_context.py` — anti-repetição por contexto
- `core/sales_flow_engine.py` — motor de diálogo (máquina de estados)
- `core/job_scheduler.py` — HumanRateLimiter + fila alternada
- `scripts/vps/internal_browser_agent.py` — loop do agente
- `scripts/vps/internal_browser.py` — cliente CDP
- `tests/` — 276 testes
- `CONTEXTO_PROJETO.md` — este arquivo
