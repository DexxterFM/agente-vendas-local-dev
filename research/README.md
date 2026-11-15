# Pesquisa comercial — 13/11/2026

Seis fichas em `sales_research.json`, com resumos originais, fontes primárias e aplicação proposta ao ERP. São importadas uma única vez na biblioteca local e indexadas no RAG. Não contêm cópias de livros completos nem alegações de resultado comercial já comprovado neste projeto.

Fontes: Huthwaite (SPIN); Guilford (Miller e Rollnick); página de Robert Cialdini (Influence); artigo de Huang e colegas na Harvard Business School; reanálise de Kluger e Malloy no PMC. A sexta ficha é uma síntese original para o atendimento do ERP.

Fluxo: responder à mensagem atual → reconhecer contexto → escolher pergunta ou informação útil → comparar somente fatos documentados → propor teste se houver interesse → orientar instalação um passo por vez pelo link cadastrado. Os exemplos servem de orientação e não são respostas prontas.

Fila: pausa mínima padrão de 7 segundos a partir do enfileiramento, configurável entre 3 e 30. O relógio não bloqueia a interface. O aplicativo verifica a fila enquanto está aberto. Respostas aprovadas são enviadas ao vencer o prazo, desde que o contexto não tenha mudado e a conversa não esteja pausada. Uma nova mensagem invalida a resposta aguardando; falhas ambíguas exigem conferência, sem reenvio automático.

A geração consulta o histórico, a personalidade e os trechos do RAG antes de produzir a resposta. A fila utiliza o conector oficial Graph API; não simula digitação na tela. A operação real ainda depende da conta Meta configurada e do recebimento/sincronização das mensagens. Testes locais usam remetente simulado e não demonstram entrega real no Instagram.
