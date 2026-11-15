# Evidências REA — estado anterior à evolução v0.3

Data da inspeção: 2026-11-12  
Ferramenta: REA 6.9.0 (MCP, modo somente leitura)

## Executável legado

- Arquivo: `dist/SalesAgentLocalV2.exe`
- SHA-256: `60866331bf1a24b211f0da85fc7aa2fb7fe17e2d5056075ee5103222db7a155e`
- Formato: PyInstaller, layout 2.1
- Python empacotado: 3.15 (`python315.dll`)
- Entradas no container: 1.005
- Nós/ocorrências/arestas: 1.004 / 1.006 / 1.004
- Integridade: 1.005 hashes verificados, 0 divergências
- Evidence ID: `ev_bbc56ce352eeff6b46b0bb810d52c8b4eba7a8654f1b524dd63cf25abb6c69c3`
- Inventário: `ev_106a621fc2c4a4dd2a2db1e8d1ddea6341dc47b132443e445d711af575437106`

Limitações: o PYZ permanece opaco à inspeção estática; a análise não executa o
artefato nem comprova comportamento em runtime.

## Banco SQLite legado

- Arquivo: `sales_agent.sqlite3`
- SHA-256: `5186116a875cf0d1a9bff0d8ef3a4ef54b67c15742a3b9a3a8fe7d85dc01ec14`
- Tamanho: 24.576 bytes
- Engine reportada: SQLite 3.53.4
- Evidence IDs: `ev_1cb979d94a96a23b52307e62786c5b4547754a8535056b11b6ffe68d9ce70d78` (inventário),
  `ev_cbfef5d527335f8e80182f8992bbcd5f0131a8e77e825f9e72d91f2c3e2aa6e6` (leads),
  `ev_f73d346f8fd16bb7f57df71d9697faf3f462d832ec345476a1a8569fae9d5dd3` (messages)

Tabelas existentes:

1. `messages(id, role, content, created_at)`
2. `leads(id, name, contact, stage, notes, created_at)`
3. `products(id, name, price, active, created_at)`
4. `opportunities(id, lead_id, product_id, stage, value, next_action, created_at)`
5. `followups(id, lead_id, due_at, task, done, created_at)`

Ausências relevantes para a próxima versão:

- clientes, conversas e consentimentos;
- score e próxima ação estruturados no lead;
- rascunho/status/canal no follow-up;
- trilha de auditoria;
- aprovações humanas pendentes;
- índices para consultas por lead/etapa;
- configuração persistida de persona.

## Decisões orientadas por evidência

- Evoluir o schema com migrações idempotentes, sem apagar o banco existente.
- Manter as cinco primeiras colunas de `leads` na mesma ordem para compatibilidade
  com os testes e dados atuais.
- Separar o banco de desenvolvimento do banco do executável instalado, usando
  `%LOCALAPPDATA%/SalesAgentLocal` quando empacotado.
- Manter a política de leitura/navegação como allowlist e registrar toda ação em
  auditoria; ações de escrita externas permanecem sem executor automático.
