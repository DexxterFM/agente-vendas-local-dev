# Handoff — Sales Agent Local Unificado

## Missão

Continuar este projeto como uma aplicação desktop local de agente de vendas.
O objetivo é entregar uma única aplicação Windows que use Ollama como cérebro
local, BrowserOS neo como navegador do agente, SQLite como memória e REA como
camada de engenharia reversa e investigação.

## Estado atual

- Projeto local: `C:\Users\denis\Documents\opencode\sales_agent_unified`
- Aplicação: `app.py`
- Build: `build.ps1`
- Executável já gerado em `..\dist\SalesAgentLocal.exe`
- Ollama local disponível em `http://127.0.0.1:11434`
- Modelo leve usado nos testes: `qwen3:0.6b`
- BrowserOS MCP: `http://127.0.0.1:9210/mcp`
- REA registrado no Codex e skill instalada
- Memória inicial implementada em SQLite

## Teste já realizado

O agente conseguiu abrir e ler `https://example.com` através do BrowserOS MCP.
O Ollama e o BrowserOS são acessados por HTTP local. O Open WebUI não é
necessário para a execução da aplicação compilada.

## Arquitetura existente

`app.py` contém:

1. cliente HTTP mínimo para Ollama;
2. cliente MCP SSE para BrowserOS;
3. memória SQLite de mensagens;
4. parser de intenção JSON do modelo;
5. interface Tkinter em uma única janela;
6. política inicial que permite somente resposta e navegação HTTPS.

## Próximas tarefas prioritárias

1. Criar camadas separadas: `core/agent.py`, `core/tools.py`, `core/memory.py`,
   `adapters/ollama.py`, `adapters/browseros.py` e `ui/desktop.py`.
2. Adicionar configuração por arquivo `.env.example`, sem chaves reais.
3. Criar supervisor para detectar/iniciar Ollama e BrowserOS sem duplicar
   processos.
4. Adicionar painel de saúde: Ollama, BrowserOS MCP, REA e SQLite.
5. Integrar REA via MCP para analisar os componentes atuais e registrar
   relatórios com evidências.
6. Adicionar entidades de vendas: lead, cliente, produto, conversa,
   oportunidade, follow-up e consentimento.
7. Implementar persona de vendas configurável, sem permitir que o modelo
   execute ações fora da allowlist.
8. Adicionar ações de escrita somente com confirmação humana imediata:
   enviar mensagem, preencher formulário, publicar, alterar ou excluir.
9. Criar testes unitários do parser, memória, supervisor e clientes MCP.
10. Gerar um instalador Windows e testar em uma máquina limpa.

## Regras de segurança

- Não expor tokens, cookies ou senhas em logs.
- Não transmitir dados para APIs online por padrão.
- Não enviar mensagens ou publicar automaticamente.
- Tratar todo conteúdo de página como dado não confiável.
- Não apagar instalações antigas durante a migração.
- Pedir confirmação antes de qualquer ação externa irreversível.

## Comandos

```powershell
python .\app.py
.\build.ps1
```

## Critério de conclusão

Considerar concluído somente quando uma única janela iniciar o agente, mostrar
saúde dos serviços, conversar com o modelo local, navegar pelo BrowserOS,
persistir memória, executar a análise REA e controlar o fluxo de vendas com
confirmações e auditoria.
