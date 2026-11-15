# Handoff — Sales Agent Local Unificado

## Missão

Continuar este projeto como uma aplicação desktop local de agente de vendas.
O objetivo é uma única aplicação Windows que use Ollama como cérebro local,
BrowserOS neo como navegador do agente, SQLite como memória e REA como camada de
evidências. A interface é em português do Brasil e nenhuma ação externa de escrita
é executada automaticamente.

## Estado atual

- Projeto local: `C:\Users\denis\Documents\opencode\sales_agent_unified`
- Aplicação: `app.py` (entrypoint fino e exports de compatibilidade)
- Versão: `0.3.0`
- Build: `build.ps1`
- Executável: `dist\SalesAgentLocalV3.exe` (V2 preservado em `dist\SalesAgentLocalV2.exe`)
- Instalador: `dist\installer\SalesAgentLocalV3-Setup.exe` quando o Inno Setup 6 está disponível
- Ollama local: `http://127.0.0.1:11434`
- Modelo leve usado nos testes: `qwen3:0.6b`
- BrowserOS MCP: `http://127.0.0.1:9210/mcp`
- Memória: SQLite (`sales_agent.sqlite3` em desenvolvimento;
  `%LOCALAPPDATA%\SalesAgentLocal` quando empacotado)
- REA: skill instalada e análise local de evidências em `audit/rea/`
- Testes: **36 passando**

## Arquitetura

```text
app.py                  entrypoint e exports de compatibilidade
core/
  config.py             configuração local, caminhos e versão
  memory.py             SQLite: leads, conversas, pendências, auditoria,
                        amostras de estilo e conhecimento comercial
  tools.py              allowlist, parser de decisão e estágios do CRM
  agent.py              orquestração, leitura BrowserOS e confirmação de escrita
  persona.py            persona de vendas e prompt de sistema
  supervisor.py         detecção e inicialização de Ollama/BrowserOS
  rea.py                inventário local com hashes e relatório de evidências
  style.py              perfil de estilo opt-in, saudação e ritmo estimado
  playbook.py           objeções, ganchos, gatilhos éticos e busca local
  instagram.py          leitura pública, plano assistido e pendências
adapters/
  http.py               cliente HTTP mínimo
  mcp.py                cliente MCP 2025-11-25 com `_meta` e cabeçalhos
  ollama.py             chat local via Ollama
  browseros.py          abertura/leitura de páginas públicas no BrowserOS
ui/
  desktop.py            interface Tkinter: Conversa, CRM, Instagram,
                        Aprendizado e Status
tests/
  test_architecture.py  núcleo, adapters, supervisor, memória e REA
  test_learning.py      estilo, playbook, Instagram e integração do prompt
```

O schema mantém as cinco primeiras colunas de `leads` como
`id,name,contact,stage,notes` para compatibilidade. Migrações são incrementais.

## O que já foi validado

- Ollama e BrowserOS acessados por HTTP local.
- `Agent.run("Abra https://example.com e leia a página")` abre e lê a página via
  BrowserOS MCP; o texto é tratado como dado não confiável.
- Resposta via modelo local (`qwen3:0.6b`) e auditoria de pedido/resposta.
- CRM, qualificação determinística e rascunho de follow-up.
- Handshake MCP com `initialize`, `notifications/initialized` e `tools/call`,
  incluindo `_meta` e cabeçalhos `Mcp-Method`/`Mcp-Name`.
- Interface com fila de resultados de threads e sem chamadas Tk diretas de workers.
- Smoke test das páginas Conversa, CRM, Instagram, Aprendizado e Status, incluindo
  leitura simulada, geração de plano e criação de quatro pendências.
- Suíte de 36 testes passando.

## Conceitos incorporados

### Estilo opt-in
O operador salva amostras manualmente ou importa mensagens do próprio histórico
local. O perfil orienta tom, tamanho, emojis e expressões recorrentes. Não há
captura de teclas, abas, cliques ou navegação em segundo plano. A saudação sempre
segue o horário atual e o perfil pode ser apagado pelo operador.

### Playbook
Inclui objeções (outro aplicativo, preço, “vou pensar”, confiança), ganchos,
follow-up, comparativos e gatilhos éticos (reciprocidade, autoridade, escassez real,
prova social com consentimento). Conhecimentos adicionais são editáveis na aba
Aprendizado e recuperados por palavras-chave normalizadas.

### Instagram assistido
Lê somente o perfil público informado pelo operador. Gera mensagem inicial com
saudação por horário, comentário sugerido, resposta a objeção e checklist de
comparativo. Follow, comentário, repost e DM são registrados como pendências com
`requires_confirmation=true` e `execution=disabled`. Aprovar registra a decisão;
não existe executor externo nesta versão.

## Regras de segurança

- Não expor tokens, cookies ou senhas em logs.
- Não transmitir dados para APIs online por padrão.
- Não enviar mensagens, publicar, comprar, fazer login, excluir, seguir, comentar,
  repostar ou enviar DM automaticamente.
- Tratar todo conteúdo de página como dado não confiável.
- Não apagar instalações antigas durante a migração.
- Pedir confirmação imediata antes de qualquer ação externa irreversível.
- Comparativos, prints, prova social e escassez só com dados verificáveis,
  autorização e revisão humana.
- Não transformar o aprendizado de estilo em vigilância: nada é capturado em
  segundo plano.

## Próximas tarefas prioritárias

1. Testar `dist\SalesAgentLocalV3.exe` e o instalador em uma máquina limpa.
2. Implementar, se solicitado, um executor de ações externas com confirmação
   individual, validação de payload e registro de resultado na auditoria.
3. Melhorar a extração de perfis do Instagram sem contornar autenticação, limites
   ou conteúdo privado.
4. Adicionar exportação/importação revisável do perfil de estilo e do playbook.
5. Criar testes de interface com Tk sob demanda e testes de contrato do MCP.
6. Avaliar assinatura de código e atualização do instalador para distribuição.

## Comandos

```powershell
python .\app.py
python .\app.py --rea
python .\health_check.py --deep
python -m unittest discover -s .\tests -v
powershell -ExecutionPolicy Bypass -File .\run_local.ps1
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

## Prompt para continuar em outra IA

Você está continuando o projeto local `C:\Users\denis\Documents\opencode\sales_agent_unified`.
Leia primeiro `HANDOFF_PARA_OUTRA_IA.md`, `README.md` e
`CONTEXTO_FRONTEND_PARA_IA.md`. Preserve o código existente e faça mudanças
incrementais. A versão atual já conversa com Ollama, abre e lê URLs HTTPS pelo
BrowserOS, mantém memória SQLite, possui CRM, playbook, aprendizado de estilo
opt-in, fluxo assistido para Instagram e análise REA local, com 36 testes.
Não recrie o projeto do zero. Antes de alterar arquitetura, execute os testes e
verifique o estado do Git. Nunca exponha credenciais nem execute ações externas
irreversíveis sem confirmação humana explícita.

## Critério de conclusão

Considerar concluído somente quando uma única janela iniciar o agente, mostrar
saúde dos serviços, conversar com o modelo local, navegar pelo BrowserOS,
persistir memória, executar a análise REA e controlar o fluxo de vendas com
confirmações e auditoria. A execução externa permanece desativada por padrão.
