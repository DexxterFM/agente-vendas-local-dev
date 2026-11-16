#!/usr/bin/env bash
# Recupera somente um renderizador que deixou de responder por três leituras
# consecutivas. O perfil persistente não é removido nem alterado.
set -euo pipefail
DATA_DIR=/var/lib/agente-vendas-local/diagnostics
REQUEST="$DATA_DIR/browser-recovery.request"
COOLDOWN="$DATA_DIR/browser-recovery.cooldown"
NOW=$(date +%s)

if [[ ! -s "$REQUEST" ]]; then
  exit 0
fi

if [[ -f "$COOLDOWN" ]] && (( NOW - $(cat "$COOLDOWN") < 600 )); then
  exit 0
fi

printf '%s\n' "$NOW" > "$COOLDOWN"
rm -f "$REQUEST"
systemctl restart agente-vendas-internal-browser.service
