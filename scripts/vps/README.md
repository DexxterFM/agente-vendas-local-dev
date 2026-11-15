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

## Variáveis do worker

```text
SALES_AGENT_DATA_DIR=/var/lib/agente-vendas-local
SALES_AGENT_CYCLE_SECONDS=30
SALES_AGENT_AUTO_DISPATCH=false
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:1.7b
INSTAGRAM_ACCESS_TOKEN=
IG_BUSINESS_ACCOUNT_ID=
```

Depois de conferir que a conta Meta e a fila estão corretas, `SALES_AGENT_AUTO_DISPATCH=true`
permite o despacho das respostas que a integração oficial aceitar. A conta deve
estar ativa no banco local (`sales.agent.active=true`).

## Verificação

```bash
systemctl status agente-vendas-worker --no-pager
journalctl -u agente-vendas-worker -f
```
