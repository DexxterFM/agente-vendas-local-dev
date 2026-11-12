# Agente de Vendas Local Unificado

Aplicação desktop própria, sem depender do Open WebUI durante a operação.

Execute com `python .\\sales_agent_unified\\app.py`.

Pré-requisitos: Ollama com o modelo definido em `OLLAMA_MODEL` e BrowserOS neo
com MCP em `http://127.0.0.1:9210/mcp`.

Para compilar: `pyinstaller --noconfirm --onefile --windowed --name SalesAgentLocal .\\sales_agent_unified\\app.py`.

Verificar serviços: `python .\\sales_agent_unified\\health_check.py`.

Executar testes: `python -m unittest discover -s .\\sales_agent_unified\\tests`.
