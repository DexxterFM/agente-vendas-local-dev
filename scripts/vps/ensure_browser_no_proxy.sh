#!/bin/bash
# Garante que o navegador interno da VPS use a internet direta, sem depender
# do túnel SOCKS5 (127.0.0.1:1080) aberto pelo computador do operador.
# Quando o PC entra em repouso esse túnel cai e o navegador perde o acesso ao
# Instagram. A VPS tem saída direta, então o proxy não é necessário.
set -e

UNIT="/etc/systemd/system/agente-vendas-internal-browser.service"

if [ ! -f "$UNIT" ]; then
  echo "Service não encontrado: $UNIT"
  exit 1
fi

if ! grep -q 'proxy-server' "$UNIT"; then
  echo "OK: navegador já usa conexão direta (sem proxy)."
  exit 0
fi

BACKUP="${UNIT}.bak-proxy-$(date +%Y%m%d-%H%M%S)"
cp "$UNIT" "$BACKUP"
echo "Backup criado: $BACKUP"

sed -i 's| --proxy-server=socks5://127.0.0.1:1080||' "$UNIT"
sed -i 's| --proxy-bypass-list=127.0.0.1,localhost||' "$UNIT"
systemctl daemon-reload
systemctl restart agente-vendas-internal-browser

for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
    echo "Navegador pronto após ${i}s (proxy removido)."
    break
  fi
  sleep 1
done

echo "ExecStart atual:"
grep '^ExecStart=' "$UNIT"
