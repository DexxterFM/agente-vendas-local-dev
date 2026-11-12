# Agente de Vendas Local Unificado

Aplicação desktop própria, sem depender do Open WebUI durante a operação. O código reúne conversa com persona de vendas, memória SQLite, CRM de leads, qualificação determinística e rascunhos de follow-up. Nenhuma mensagem externa é enviada automaticamente.

Execute com `python .\\sales_agent_unified\\app.py`.

Pré-requisitos: Ollama com o modelo definido em `OLLAMA_MODEL` e BrowserOS neo
com MCP em `http://127.0.0.1:9210/mcp`.

Executável compilado: `dist\\SalesAgentLocalV2.exe`.

Para iniciar a aplicação e tentar ativar os serviços locais automaticamente: `powershell -ExecutionPolicy Bypass -File .\\run_local.ps1`.

Para compilar novamente: `powershell -ExecutionPolicy Bypass -File .\\build.ps1`.

Verificar serviços: `python .\\sales_agent_unified\\health_check.py`.

Executar testes: `python -m unittest discover -s .\\sales_agent_unified\\tests`.
