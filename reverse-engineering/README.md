# Relatório REA

Foi executada uma análise estática completa do `app.asar` do Open WebUI local:

- alvo: `C:\Users\denis\AppData\Local\Programs\open-webui\resources\app.asar`
- arquivos examinados: 6.337 no view final
- evidência completa: `open-webui-evidence.json` (arquivo local, ignorado pelo Git)
- evidência REA: `ev_79a4aca3c1d2c92e9bea7f19c32c8c922ea5b62d0b19b53c5d283653c1e73737`

Conclusão inicial: o Open WebUI é um aplicativo Electron com uma camada de
interface e integração de modelos/serviços. A nova aplicação deve manter apenas
os contratos necessários (Ollama, MCP, memória e auditoria), sem copiar o
empacotamento ou a grande árvore de dependências do Open WebUI.

As limitações do REA permanecem registradas no bundle, incluindo relações
dinâmicas não resolvidas e fatos estáticos que não provam comportamento em
runtime. Use a evidência para orientar decisões, não como autorização para
copiar código proprietário.
