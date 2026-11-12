# Registro do projeto — Agente de Vendas

## O que foi solicitado

- Criar um aplicativo próprio para um agente de vendas.
- Unificar conversa, memória, CRM, navegador e modelo em uma aplicação.
- Usar Ollama como possibilidade de modelo local.
- Usar BrowserOS como navegador controlado pelo agente.
- Permitir que o agente abra e leia páginas pelo navegador.
- Criar memória local para histórico de conversas e leads.
- Criar qualificação de leads por intenção de compra.
- Criar rascunhos de follow-up para clientes.
- Criar uma interface visual própria para interação com o agente.
- Criar um frontend com conversa, CRM e painel de status.
- Preparar documentação para outra IA continuar o projeto.
- Configurar o OpenCode para usar provedores compatíveis com OpenAI.
- Investigar e corrigir o fechamento do OpenCode.

## Projeto entregue até agora

- Aplicação desktop própria em Python/Tkinter.
- Memória SQLite.
- CRM de leads.
- Qualificação determinística: novo, morno ou quente.
- Geração de follow-up como rascunho.
- Integração HTTP com Ollama.
- Integração MCP com BrowserOS.
- Comando direto para abrir uma URL HTTPS e ler seu conteúdo.
- Aba de status para Ollama, BrowserOS e modelo configurado.
- Inicializador local `run_local.ps1`.
- Executável Windows `SalesAgentLocalV2.exe`.
- Briefing visual em `CONTEXTO_FRONTEND_PARA_IA.md`.
- Handoff para outra IA em `HANDOFF_PARA_OUTRA_IA.md`.

## Interação projetada

O usuário conversa naturalmente com o agente, por exemplo:

> Abra uma página, leia as informações e me diga o que é importante para a venda.

O agente deve:

1. Entender a intenção do usuário.
2. Abrir o navegador dedicado quando houver um pedido explícito de navegação.
3. Ler a página e retornar um resumo útil.
4. Identificar necessidades, dúvidas e sinais de compra.
5. Atualizar o lead no CRM quando solicitado.
6. Preparar uma resposta comercial ou um follow-up.
7. Mostrar claramente quando algo é apenas um rascunho ou uma sugestão.

## Experiência desejada

- Conversa natural em português do Brasil.
- Tom consultivo, persuasivo e cordial.
- Poucas telas e operação centralizada.
- Resposta rápida e objetiva.
- Navegação visível e compreensível.
- Histórico persistente.
- Lead, etapa, score e próxima ação sempre fáceis de localizar.
- Possibilidade de substituir o modelo local por um provedor compatível com OpenAI.

## Provedores considerados

- Ollama local com modelo leve.
- Drael compatível com OpenAI, modelo `drael-v1`, endpoint `https://drael.sh/v1`.
- Endpoint Tor do Drael como alternativa condicionada à existência de um proxy Tor ativo.

## Direção do projeto

O objetivo é uma experiência integrada e natural, com o agente entendendo conversa, vendas e navegação. O projeto deve manter separadas as funções de raciocínio, memória, CRM, navegador e interface, para que outra IA possa evoluir cada parte sem recriar o sistema.

Este arquivo é somente um registro de requisitos e visão do produto. Credenciais, chaves, cookies e instruções para remover proteções não devem ser armazenados aqui.
