# Molde funcional — Agente de Vendas Social

## Visão do produto

Um agente comercial conectado a canais digitais, capaz de organizar leads, entender conversas, preparar abordagens personalizadas, acompanhar oportunidades e executar rotinas de relacionamento autorizadas.

O agente atua como um vendedor digital: identifica contexto, escolhe o melhor momento de contato, adapta o tom da mensagem, registra cada interação e conduz o lead até o próximo passo comercial.

## Objetivos principais

- Encontrar oportunidades dentro de contatos autorizados.
- Organizar leads por origem, interesse, etapa e potencial.
- Personalizar mensagens com base no histórico de cada pessoa.
- Responder conversas de forma natural e consultiva.
- Planejar sequências de acompanhamento.
- Publicar conteúdos comerciais aprovados.
- Medir respostas, conversões e qualidade dos contatos.
- Manter toda a operação em um painel único.

## Estrutura geral

### 1. Interface do agente

Painel central com:

- Conversas abertas.
- Leads prioritários.
- Campanhas ativas.
- Tarefas de hoje.
- Respostas pendentes.
- Indicadores de conversão.
- Status do navegador, modelo e memória.

### 2. Cérebro comercial

O núcleo de IA interpreta cada evento e decide o próximo passo comercial:

- Classificar intenção.
- Detectar interesse, dúvida, objeção ou compra.
- Escolher uma abordagem adequada.
- Resumir a conversa.
- Sugerir produto ou serviço.
- Criar resposta personalizada.
- Definir prazo de retorno.
- Encaminhar para atendimento humano quando necessário.

### 3. Memória e CRM

Cada lead possui um perfil persistente:

- Nome e identificadores do canal.
- Origem do contato.
- Preferências declaradas.
- Histórico de mensagens.
- Produtos de interesse.
- Etapa do funil.
- Score de intenção.
- Último contato.
- Próximo follow-up.
- Consentimento e preferências de comunicação.
- Observações comerciais.

### 4. Adaptador de navegador

O navegador dedicado permite operar interfaces web autorizadas:

- Abrir páginas.
- Ler conversas e informações visíveis.
- Localizar campos e botões.
- Preencher mensagens preparadas.
- Acompanhar notificações.
- Confirmar o resultado da ação.
- Registrar evidência da execução.

### 5. Gerenciador de campanhas

Campanhas são compostas por:

- Nome e objetivo.
- Público selecionado.
- Produto ou oferta.
- Tom de voz.
- Sequência de mensagens.
- Intervalo entre contatos.
- Horário permitido.
- Critérios de pausa.
- Métrica de sucesso.

Uma campanha pode criar tarefas de abordagem, acompanhamento, resposta e conteúdo, sempre respeitando os contatos e canais autorizados.

## Fluxo de venda

1. Um lead entra no CRM.
2. O agente identifica origem e contexto.
3. A IA classifica o estágio: novo, interessado, qualificado, proposta ou cliente.
4. O agente escolhe uma mensagem adequada.
5. A mensagem é personalizada com dados reais do histórico.
6. O sistema registra a interação.
7. Uma próxima ação é criada.
8. Respostas do lead atualizam o score e o estágio.
9. Objeções são classificadas.
10. O agente sugere solução, produto ou encaminhamento.
11. A conversão gera oportunidade e tarefa de pós-venda.

## Tipos de interação

### Mensagens diretas

- Saudação contextual.
- Resposta a uma pergunta recebida.
- Apresentação de produto solicitado.
- Recuperação de conversa interrompida.
- Follow-up de proposta.
- Confirmação de reunião ou atendimento.

### Relacionamento social

- Acompanhar perfis relacionados ao público autorizado.
- Interagir com publicações relevantes.
- Responder comentários relacionados ao produto.
- Compartilhar conteúdos comerciais aprovados.
- Registrar cada interação no histórico do lead.

### Conteúdo

- Criar legenda.
- Sugerir imagem ou vídeo.
- Preparar variações de chamada.
- Reaproveitar conteúdo aprovado.
- Programar publicação em calendário.
- Medir alcance, resposta e conversão.

## Personalidade do vendedor

- Cordial.
- Consultivo.
- Claro.
- Persuasivo sem ser agressivo.
- Focado em benefício e contexto.
- Capaz de reconhecer dúvidas.
- Nunca inventa preço, prazo, disponibilidade ou depoimento.
- Usa linguagem natural em português do Brasil.

## Motor de decisão

Cada evento passa por esta sequência:

1. Ler o contexto.
2. Recuperar memória do lead.
3. Identificar intenção.
4. Avaliar oportunidade.
5. Escolher objetivo comercial.
6. Montar resposta ou ação.
7. Validar dados e canal.
8. Executar a tarefa autorizada.
9. Registrar resultado.
10. Agendar o próximo passo.

## Módulos do sistema

- `ConversationManager`: conversa e contexto.
- `LeadManager`: cadastro e qualificação.
- `CampaignManager`: campanhas e sequências.
- `MessageComposer`: mensagens personalizadas.
- `BrowserController`: operações no navegador.
- `MemoryStore`: histórico e preferências.
- `ProductCatalog`: produtos, preços e disponibilidade.
- `OpportunityManager`: oportunidades e propostas.
- `FollowupScheduler`: retornos e lembretes.
- `ContentPlanner`: calendário e reutilização de conteúdo.
- `Analytics`: métricas e relatórios.
- `AuditLog`: registro completo das ações.
- `HealthMonitor`: estado dos serviços e integrações.

## Dados de uma ação social

```text
id
canal
conta_de_origem
lead_id
tipo_de_acao
conteudo
contexto
campanha
data_planejada
data_executada
resultado
resposta_recebida
proxima_acao
```

## Dados de uma mensagem

```text
id
lead_id
canal
texto_original
texto_gerado
objetivo_comercial
produto_relacionado
tom
status
data_criacao
data_envio
resposta
```

## Painel de acompanhamento

### Visão diária

- Novos leads.
- Conversas respondidas.
- Follow-ups do dia.
- Propostas abertas.
- Vendas concluídas.
- Conteúdos publicados.
- Taxa de resposta.

### Visão de campanha

- Pessoas alcançadas.
- Respostas recebidas.
- Leads qualificados.
- Reuniões marcadas.
- Propostas geradas.
- Conversões.
- Custo por oportunidade.

### Visão individual do lead

- Timeline completa.
- Última mensagem.
- Intenção atual.
- Objeções.
- Produtos vistos.
- Próxima ação.
- Rascunho recomendado.

## Experiência de uso

O operador abre uma única aplicação e encontra:

- Uma caixa de conversa com o agente.
- Uma lista de leads prioritários.
- Um calendário de follow-ups.
- Um construtor de campanhas.
- Uma biblioteca de mensagens.
- Um painel de métricas.
- Um navegador integrado para as tarefas web.

O agente explica o motivo de cada recomendação, mostra o conteúdo antes de uma ação relevante e mantém uma trilha de auditoria da operação.

## Resultado esperado

Uma central de vendas capaz de unir atendimento, CRM, relacionamento, conteúdo, navegação e análise comercial em um único fluxo. O agente deve parecer um vendedor experiente que conhece o histórico de cada lead, trabalha com cadência, aprende com as respostas e mantém a operação organizada.

## Fluxo específico para Instagram

### Início manual pelo operador

O operador inicia pessoalmente o contato no Instagram:

- Segue o perfil da empresa.
- Curte uma publicação.
- Faz um comentário manual relacionado ao conteúdo.
- Envia uma saudação inicial, como “Bom dia”, “Boa tarde” ou “Boa noite”.

O agente não inicia essa primeira abordagem. Ele começa a trabalhar quando a empresa responde à conversa.

### Leitura do contexto da empresa

Ao detectar a resposta, o agente reúne o contexto público disponível:

- Nome e descrição do perfil.
- Segmento da empresa.
- Produtos e serviços apresentados.
- Cidade ou área de atuação.
- Publicações recentes.
- Linguagem usada pela empresa.
- Comentários e sinais de necessidade comercial.
- Histórico da conversa atual.

Esse contexto é resumido e salvo no CRM para que as próximas respostas mantenham continuidade.

### Início automático da conversa comercial

Depois que a empresa responde à saudação manual, o agente:

1. Identifica a mensagem recebida.
2. Recupera o perfil e o histórico do lead.
3. Classifica a intenção da resposta.
4. Escolhe a etapa correspondente do roteiro.
5. Gera uma resposta curta e natural.
6. Insere a resposta no campo de DM.
7. Usa a ação de colar ou digitação controlada para preencher o texto.
8. Aguarda a confirmação do resultado.
9. Registra a mensagem no CRM.
10. Atualiza o próximo passo da conversa.

### Roteiro de respostas do vendedor

O roteiro é adaptável, não uma sequência fixa de copiar e colar. Cada etapa possui objetivo, perguntas e respostas possíveis:

#### Etapa 1 — Acolhimento

Responder à saudação e reconhecer a empresa ou o conteúdo visto.

#### Etapa 2 — Descoberta

Fazer uma pergunta curta para entender como a empresa trabalha, qual problema enfrenta ou o que deseja melhorar.

#### Etapa 3 — Qualificação

Identificar necessidade, urgência, orçamento, autoridade de decisão e prazo.

#### Etapa 4 — Conexão com a solução

Apresentar somente o benefício relacionado ao que a empresa informou.

#### Etapa 5 — Tratamento de objeção

Reconhecer a dúvida, esclarecer com linguagem simples e propor o próximo passo.

#### Etapa 6 — Conversão

Convidar para orçamento, demonstração, reunião ou envio de informações.

#### Etapa 7 — Follow-up

Se a resposta parar, registrar a data e preparar uma retomada contextualizada.

### Comportamento de escrita

Para parecer uma conversa humana e evitar respostas artificiais:

- Digitar ou colar uma mensagem por vez.
- Usar frases curtas.
- Respeitar o ritmo da conversa.
- Não enviar blocos longos sem necessidade.
- Evitar repetir a mesma abertura.
- Aproveitar palavras usadas pela própria empresa.
- Esperar a resposta antes de avançar de etapa.
- Manter uma pequena variação natural entre respostas equivalentes.

### Estado da conversa

```text
aguardando_resposta
empresa_respondeu
contexto_lido
descoberta
qualificacao
solucao_apresentada
objecao
proposta
followup
encerrada
```

### Memória específica do DM

```text
instagram_handle
nome_empresa
segmento
perfil_resumido
publicacoes_relevantes
saudacao_inicial
mensagens_recebidas
mensagens_enviadas
necessidades
objecoes
produtos_de_interesse
etapa_atual
ultima_resposta
proximo_passo
data_do_followup
```

### Painel do vendedor

O operador deve conseguir visualizar:

- Conversas aguardando resposta.
- Empresas que responderam recentemente.
- Etapa de cada conversa.
- Resumo do perfil.
- Próxima resposta sugerida.
- Texto que será colado na DM.
- Histórico completo.
- Botão para pausar ou retomar o agente naquela conversa.
