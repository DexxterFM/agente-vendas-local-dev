# Briefing visual — Agente de Vendas Local Unificado

## Objetivo

Criar uma imagem/conceito de frontend para um aplicativo desktop de agente de vendas com inteligência artificial local. A interface deve transmitir confiança, agilidade, organização e controle humano. Não é um chatbot genérico: é uma central de atendimento e CRM para um vendedor assistido por IA.

## O agente

O agente é um vendedor digital consultivo, cordial e objetivo. Ele conversa em português do Brasil, entende a necessidade do cliente, identifica intenção de compra, sugere o próximo passo e mantém o histórico da conversa. Ele usa um modelo local via Ollama e pode operar um navegador dedicado via BrowserOS para abrir e ler páginas públicas.

O agente nunca deve parecer agressivo, enganoso ou autônomo sem limites. Ele não deve enviar mensagens, publicar, comprar, fazer login, excluir dados ou alterar informações sem confirmação humana. A personalidade visual deve ser profissional, humana e prestativa — mais próxima de um especialista comercial do que de um robô futurista.

## Produto

Nome sugerido na interface: **Sales Agent Local** ou **Agente de Vendas Local**.

Aplicação desktop unificada, com modelo local, memória SQLite, CRM de leads e integração segura com BrowserOS. A tela principal deve funcionar bem em 1280×800, com layout responsivo para janelas menores.

## Tela principal desejada

Criar um dashboard com três áreas:

### 1. Barra lateral

- Logo simples: balão de conversa combinado com uma pequena seta de crescimento.
- Nome do produto: “Agente de Vendas Local”.
- Navegação: **Conversa**, **CRM**, **Status**.
- Indicador discreto “Local / Privado”.
- Rodapé com modelo atual: `qwen3:0.6b`.

### 2. Área central de conversa

- Cabeçalho: “Conversa com o agente”.
- Subtítulo: “Seu vendedor assistido por IA local”.
- Mensagens em balões limpos, com o agente à esquerda e o usuário à direita.
- Mensagem de exemplo do usuário: “Abra https://example.com e leia a página”.
- Resposta de exemplo do agente: “Abri a página no BrowserOS e encontrei as informações principais.”
- Campo de texto grande na parte inferior.
- Botão principal: **Enviar**.
- Botão secundário opcional: **Abrir no navegador**.
- Selo de segurança: “Nenhuma ação externa é executada sem autorização”.

### 3. Painel lateral direito ou painel inferior

Mostrar um resumo comercial:

- Lead selecionado: nome, contato e etapa.
- Etapas visuais: Novo, Qualificado, Quente.
- Score de intenção, por exemplo `78/100`.
- Próximo passo sugerido.
- Botão **Gerar follow-up**.
- O follow-up deve aparecer como rascunho, com indicação “Não enviado”.

## Aba CRM

Visualizar uma tabela de leads com:

- Nome.
- Contato.
- Etapa.
- Score.
- Última interação.
- Próxima ação.

Adicionar um formulário “Novo lead” com nome e contato. Incluir uma área “Mensagem recebida” e o botão **Qualificar lead**. Depois da qualificação, exibir razões como “perguntou sobre preço”, “demonstrou intenção de compra” e “indicou urgência”.

## Aba Status

Mostrar os componentes locais como cartões de saúde:

- Ollama — API local — conectado.
- Modelo — `qwen3:0.6b`.
- BrowserOS MCP — conectado.
- Memória SQLite — ativa.
- Privacidade — dados processados localmente.

Usar pontos verdes para conectado, amarelos para atenção e vermelhos para indisponível. Incluir botão **Atualizar status**.

## Direção visual

- Estilo: SaaS premium, desktop profissional, moderno e calmo.
- Fundo: azul-marinho quase preto ou grafite azulado.
- Superfícies: cartões em azul escuro, com bordas sutis.
- Cor de destaque: turquesa/verde-água para ações positivas.
- Cor de conversão: âmbar discreto para lead quente.
- Tipografia: sans-serif limpa, semelhante a Inter ou Segoe UI.
- Cantos levemente arredondados, sombras suaves, bastante espaço negativo.
- Ícones lineares simples; evitar excesso de gradientes, neon, hologramas e estética de ficção científica.
- Acessibilidade: contraste alto, textos legíveis e estados não comunicados apenas por cor.

## Elementos que não devem aparecer

- Não mostrar logotipos do Open WebUI, ChatGPT ou outras plataformas.
- Não representar o agente como um humanoide ou mascote infantil.
- Não mostrar ações perigosas como “Enviar automaticamente”, “Comprar agora” ou “Publicar”.
- Não inventar WhatsApp, Instagram ou Gmail como integrações já prontas.
- Não exibir chaves de API, senhas ou dados reais de clientes.
- Não usar textos em inglês como idioma principal.

## Prompt curto para geração da imagem

“Interface desktop premium em português do Brasil para um Agente de Vendas Local com IA, modelo local Qwen via Ollama e navegador BrowserOS. Dashboard escuro em azul-marinho, detalhes turquesa, sidebar com Conversa, CRM e Status, chat consultivo no centro, painel de lead com score de intenção e rascunho de follow-up à direita, cartões de saúde mostrando Ollama e BrowserOS conectados. Visual profissional, confiável, humano e organizado, estilo SaaS moderno, alta legibilidade, sem logotipos de terceiros, sem estética futurista exagerada, sem ações automáticas perigosas.”

## Regra de fidelidade

A imagem é uma referência visual para implementar o frontend. Preserve a arquitetura funcional: conversa, CRM, status dos serviços, memória local, qualificação de leads e navegação segura somente quando solicitada pelo usuário.
