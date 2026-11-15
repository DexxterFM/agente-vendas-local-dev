# Estado verificado — 0.7.0

Janela Electron com recursos próprios. Teste real do executável empacotado confirmou a renderização e uma consulta ao backend SQLite (`backend: true`).

Implementado: ponte IPC isolada, cadastro de leads, histórico, registro manual de mensagens, chamada ao Ollama, persistência da fila, pausa, follow-up, biblioteca e diagnóstico. A integração Meta agora pertence ao aplicativo local: lê token/conta da memória local ou `.env`, possui geração de URL OAuth e troca de código por token de longa duração, importa histórico e envia pela Graph API oficial. PostFlow permanece somente como adaptador opcional (`META_PROVIDER=postflow`), não como requisito.

Credencial Meta da conta `@erpclinicatea` foi recuperada do cofre autorizado da VPS, validada pela Graph API e salva somente na memória local do agente (o valor nunca é registrado neste documento). A importação de DMs foi iniciada, mas a Meta devolveu `403 Application request limit reached`; a rotina foi ajustada para trabalhar em lotes, pular threads já importadas e retomar sem duplicação.

Pendente: retomar a sincronização após a janela de limite da Meta, testar envio com a conta autorizada, campanhas completas, edição completa do roteiro e ligação de todos os botões secundários. A interface ainda contém elementos herdados do mockup que precisam de revisão.

Nenhuma credencial é incluída no pacote. A montagem usa uma lista explícita de diretórios permitidos e exclui bancos locais e arquivos `.env`.
