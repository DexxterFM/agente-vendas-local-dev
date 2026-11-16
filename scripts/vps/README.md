# Operação 24 horas no VPS

Este worker usa a integração oficial Meta/Instagram. O navegador interno e a
leitura da tela do Instagram continuam no computador Windows do operador.

## Instalação

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin agentevendas
sudo mkdir -p /opt/agente-vendas-local /etc/agente-vendas-local
sudo chown -R agentevendas:agentevendas /opt/agente-vendas-local
sudo cp scripts/vps/agente-vendas-worker.service /etc/systemd/system/
sudo install -m 600 -o root -g agentevendas /dev/null /etc/agente-vendas-local/agent.env
sudo systemctl daemon-reload
sudo systemctl enable --now agente-vendas-worker
```

`/etc/agente-vendas-local/agent.env` contém os valores reais de Meta/ERP e
SQLite em volume persistente. Nunca versionar esse arquivo.

Quando a conexão Meta já estiver no cofre criptografado do AvanthCode, execute
o serviço `agente-vendas-meta-vault.service` antes do worker. Ele exporta só as
variáveis indispensáveis para um `EnvironmentFile` protegido; não registra
token em logs nem no repositório.

## Operação independente por API Meta

Para operar sem o computador do operador, o agente usa a API oficial e recebe
novas DMs no webhook HTTPS abaixo:

```text
https://avanthcode.com/api/meta/webhook
```

O endpoint aceita somente `GET` de verificação com `META_WEBHOOK_VERIFY_TOKEN`
e `POST` com `X-Hub-Signature-256` válido, calculado com
`INSTAGRAM_APP_SECRET`/`META_APP_SECRET`. DMs são importadas de modo
idempotente e entram no mesmo fluxo de qualificação. Curtidas, reações,
menções e eventos sem texto são ignorados e nunca disparam resposta.

Inclua `scripts/vps/agente-vendas-meta-webhook.conf` no servidor HTTPS de
`avanthcode.com`, valide com `nginx -t` e recarregue o Nginx. O painel do
agente continua preso ao loopback da VPS.

## Variáveis do worker

```text
SALES_AGENT_DATA_DIR=/var/lib/agente-vendas-local
SALES_AGENT_CYCLE_SECONDS=30
SALES_AGENT_AUTO_DISPATCH=false
SALES_AGENT_META_SYNC_ENABLED=true
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:1.7b
INSTAGRAM_ACCESS_TOKEN=
IG_BUSINESS_ACCOUNT_ID=
META_WEBHOOK_VERIFY_TOKEN=
INSTAGRAM_APP_SECRET=
```

Depois de conferir que a conta Meta e a fila estão corretas, `SALES_AGENT_AUTO_DISPATCH=true`
permite o despacho das respostas que a integração oficial aceitar. A conta deve
estar ativa no banco local (`sales.agent.active=true`).

## Verificação

```bash
systemctl status agente-vendas-worker --no-pager
journalctl -u agente-vendas-worker -f
```
