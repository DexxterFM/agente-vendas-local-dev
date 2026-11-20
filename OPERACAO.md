# Operação do painel do agente

Guia para instalar e operar o painel em uma máquina Windows nova. O pacote
contém dois aplicativos independentes:

- **Agente de Vendas Local** — painel com backend Python e navegador próprio.
- **Agente de Vendas — Controle VPS** — painel que abre um túnel SSH e opera o
  agente já instalado na VPS (prospecção, DM, comentários e ativação por token).

## 1. Pré-requisitos

- Windows 10/11 x64.
- OpenSSH Client (instalado por padrão no Windows 10/11; verifique com `where ssh`).
- Acesso SSH à VPS com chave já autorizada (o painel usa `BatchMode=yes`, ou seja,
  **não pede senha**).
- Para gerar o instalador a partir do código-fonte: Node.js, Python 3.11+,
  PyInstaller e Inno Setup 6.

## 2. Instalação

Execute `AgenteVendasControleVPS-Setup.exe` (ou `AgenteVendasLocal-Setup.exe`).
O instalador é por usuário, não pede administrador e cria estes atalhos:

- `Agente de Vendas - Controle VPS` — abre o painel.
- `Configurar conexao VPS` — solicita o host SSH e grava a conexão.
- `Operar agente - status` — consulta os serviços da VPS por SSH.

O host **não** vem fixo no instalador. Na primeira execução do painel, use
`Configurar conexao VPS`.

## 3. Configurar a conexão

### 3.1. Chave SSH e alias (recomendado)

Crie ou edite `%USERPROFILE%\.ssh\config`:

```sshconfig
Host minha-vps
    HostName 192.0.2.10
    Port 22
    User root
    IdentityFile ~/.ssh/id_ed255ito
    IdentitiesOnly yes
```

Depois rode, no PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\configurar-conexao.ps1 -SshHost minha-vps
```

O script testa a conexão com `ssh <host> true`, valida as portas e grava:

```
%APPDATA%\AgenteVendasControleVPS\remote-control.json
{
  "enabled": true,
  "sshHost": "minha-vps",
  "localPort": 8787,
  "remotePort": 8787,
  "sshOptions": "-o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3"
}
```

Se a VPS expuser o RPC em outra porta, ajuste `-LocalPort` e `-RemotePort`.
Para não testar a conexão neste momento, use `-SkipConnectionTest`.

## 4. Operação diária

### 4.1. Abrir o painel

Clique no atalho `Agente de Vendas - Controle VPS`. O Electron abre o túnel:

- `-L 8787:127.0.0.1:8787` — traz o RPC da VPS para o navegador local.

O navegador interno da VPS usa a **internet direta da própria VPS** (não depende
mais de um túnel SOCKS vindo do computador). Isso é importante: se o agente
dependesse de um túnel `-R` aberto pelo PC, ele pararia de funcionar quando o
computador entrasse em repouso, pois a conexão cairia.

> **Nota histórica:** o navegador já usou `--proxy-server=socks5://127.0.0.1:1080`
> (túnel reverso do PC). Esse proxy foi removido para que o agente funcione 24/7
> independentemente do estado do computador. Se um deploy reapresentar o proxy,
> execute no VPS:
>
> ```bash
> bash /opt/agente-vendas-local/app/scripts/vps/ensure_browser_no_proxy.sh
> ```

Não abra outro túnel manualmente; o painel já mantém o túnel RPC vivo e o
reinicia quando cai.

### 4.2. Controles na interface

| Controle | Efeito |
|---|---|
| **Ativar agente** / **Desativar agente** | Liga/desliga o processamento de DM e respostas. |
| **Ativar prospecção** / **Desativar prospecção** | Liga/desliga a busca e o engajamento em posts. |
| Alternar modo `sales` / `prospecting` | Troca o turno da fila de jobs. |
| **Criar token único** | Gera um token de demonstração de 3 meses no ERP e mostra no balão da DM. |
| **Teste de diálogo** | Permite digitar como cliente, editar a resposta e salvar na memória. |

A prospecção e as respostas automáticas só executam após login autenticado no
Instagram no navegador interno da VPS.

### 4.3. Linha de comando

Os mesmos fluxos estão disponíveis sem abrir a janela:

```powershell
.\scripts\operar-painel.ps1 -Action status   # systemctl is-active dos serviços
.\scripts\operar-painel.ps1 -Action logs     # journalctl do worker
.\scripts\operar-painel.ps1 -Action stop     # para worker e control
.\scripts\operar-painel.ps1 -Action start    # inicia control e worker
.\scripts\operar-painel.ps1 -Action configure
.\scripts\operar-painel.ps1 -Action open     # abre o painel (padrão)
```

Todos aceitam `-SshHost` para apontar para outra VPS sem alterar o arquivo de
configuração.

### 4.4. RPC direto (diagnóstico)

Com o túnel aberto:

```powershell
$body = '{"command":"status","args":{}}'
Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/rpc' -Method Post -ContentType 'application/json' -Body $body
```

Outros comandos úteis: `activationTokenGenerate`, `activationTokenStats`,
`activationTokenList`, `setAgentActive`, `setProspectingActive`,
`browserScreenCycle`, `campaignActionAudit`.

## 5. Logs e arquivos

| Arquivo | Conteúdo |
|---|---|
| `%APPDATA%\AgenteVendasControleVPS\desktop.log` | Túneis, backend e lifecycle do Electron. |
| `%APPDATA%\AgenteVendasControleVPS\browser-send.log` | Digitação por teclado e envio de balões. |
| `%APPDATA%\AgenteVendasControleVPS\remote-control.json` | Host e portas da VPS. |
| `%LOCALAPPDATA%\Local\SalesAgentLocal\sales_agent.sqlite3` | Memória, leads, tokens e configurações. |
| VPS: `journalctl -u agente-vendas-worker -f` | Ciclo do agente e auditoria. |

Na VPS, os serviços são `agente-vendas-control`, `agente-vendas-worker`,
`agente-vendas-internal-browser` e `erpclinicatea.service`.

## 6. Atualização

O instalador pode ser executado por cima da versão anterior; ele preserva
`%APPDATA%\AgenteVendasControleVPS` e o banco em `%LOCALAPPDATA%`.

Para distribuir uma versão nova a partir do código-fonte:

```powershell
powershell -ExecutionPolicy Bypass -File .\build-release.ps1 -Version 1.1.0
```

O comando roda os testes, empacota o backend, gera os dois instaladores e cria
`dist\release\AgenteVendas-1.1.0.zip` com:

- `AgenteVendasLocal-Setup.exe`
- `AgenteVendasControleVPS-Setup.exe`
- `configurar-conexao.ps1`
- `operar-painel.ps1`
- `OPERACAO.md`
- `.env.example`

Use `-SkipTests`, `-SkipBackend` ou `-SkipInstaller` para acelerar iterações
locais. O instalador remoto **nunca** embute host, token ou credencial.

## 7. Configuração avançada

Copie `.env.example` para `.env` na raiz do projeto quando for operar pelo
código-fonte. As variáveis mais usadas:

- `SALES_AGENT_DATA_DIR` / `SALES_AGENT_DB` — local do banco.
- `OLLAMA_URL`, `OLLAMA_MODEL` — LLM local.
- `ERP_CLINICATEA_API_BASE_URL`, `ERP_CLINICATEA_API_TOKEN` — CRM do ERP.
- `ERP_DEMO_TOKEN_API_KEY` — chave da rota interna de geração de tokens.
- `INSTAGRAM_*`, `META_*` — login e webhook.
- `BROWSEROS_MCP_URL`, `BROWSEROS_SERVER`, `BROWSEROS_CONFIG` — navegador local.
  `run_local.ps1` usa `BROWSEROS_SERVER`/`BROWSEROS_CONFIG` quando definidos,
  dispensando os caminhos absolutos do perfil original.

Nunca versionar `.env`, `.meta-vault\` ou `dist\`.

## 8. Solução de problemas

| Sintoma | Ação |
|---|---|
| `Controle remoto indisponível` | Rode `configurar-conexao.ps1` e confira `desktop.log`. |
| `Permission denied (publickey)` | A chave pública do operador não está autorizada na VPS. |
| Painel abre mas não lista leads | Verifique `operar-painel.ps1 -Action status` e o `journalctl` do worker. |
| Instagram sem carregar no navegador da VPS | Confira a internet direta da VPS (`curl -I https://www.instagram.com/`) e se o proxy foi reapresentado no service; rode `bash /opt/agente-vendas-local/app/scripts/vps/ensure_browser_no_proxy.sh`. |
| Sessão do Instagram perdida | Exporte a sessão com `--export-vps-session=<arquivo>` no painel local e importe na VPS. |
| Barras duplicadas ao digitar | A versão atual usa apenas `keyDown`/`keyUp`; reinstale se ainda houver `Input.insertText` no log. |
