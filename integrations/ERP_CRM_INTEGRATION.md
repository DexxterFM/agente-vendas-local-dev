# Integração CRM ERP ClinicaTEA → Agente de Vendas Local

## O que foi reutilizado

O CRM comercial do ERP define o contrato que o agente precisa: cadastro do lead (nome, Instagram, e-mail, telefone, cidade e site), qualificação (segmento, origem, plano de interesse, valor previsto, score e temperatura), operação (etapa, responsável, próxima ação, data do próximo contato e observações) e o fluxo acolhimento → descoberta → qualificação → apresentação → objeção → proposta → follow-up.

O app local usa esses mesmos conceitos no SQLite e na interface. O PostFlow continua como camada Meta/Instagram para webhook, sincronização, fila e Graph API oficial.

## Autenticação sem copiar segredos

O adaptador `erp_crm_adapter.py` usa apenas variáveis de ambiente. Não copie `.env`, cookies, banco ou valores de tokens para o repositório.

```env
ERP_CLINICATEA_API_BASE_URL=https://api.erpclinicatea.com
ERP_CLINICATEA_API_TOKEN=<token fornecido pelo administrador>
ERP_CLINICATEA_API_TIMEOUT=30
```

O token é lido somente em tempo de execução e não aparece em logs. Para produção, use o cofre/secret manager do ERP ou variável protegida do sistema operacional.

## Contrato da ponte HTTP

| Ação | Método | Rota |
|---|---:|---|
| Saúde | GET | `/health` |
| Listar leads | GET | `/api/comercial/leads` |
| Criar lead | POST | `/api/comercial/leads` |
| Atualizar lead | PATCH | `/api/comercial/leads/{id}` |
| Gerar resposta | POST | `/api/comercial/leads/{id}/generate-reply` |
| Enfileirar DM | POST | `/api/comercial/leads/{id}/instagram-dm` |

Se o backend expuser tRPC, use um gateway interno que traduza tRPC para essas rotas. Assim o agente permanece desacoplado da autenticação interna do ERP.

## Fluxo operacional

1. PostFlow recebe a DM/webhook e normaliza a conversa.
2. O agente local recupera memória e perfil do lead.
3. Score, temperatura e etapa são atualizados no CRM.
4. Ollama gera um rascunho consultivo.
5. O operador edita/aprova ou envia para a fila do PostFlow.
6. O worker oficial da Meta envia e registra o evento.
7. O próximo follow-up é salvo no CRM.
