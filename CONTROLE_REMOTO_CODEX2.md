# Controle remoto para o Codex 2

## Estado entregue

- Repositório: `https://github.com/DexxterFM/agente-vendas-local-dev.git`
- Branch de trabalho: `master`
- Commit ativo no VPS: `3f256b1`
- Release ativa no VPS: `/opt/agente-vendas-local/releases/release-20261117-3f256b1`
- Release anterior preservada para rollback: `release-20261117-flow-studio`
- Painel remoto: `127.0.0.1:8787` no VPS, exposto somente por túnel SSH.

## Abrir o painel remoto no Windows

Execute no PowerShell:

```powershell
ssh -N -L 8787:127.0.0.1:8787 erpclinicatea-vps
```

Em outra janela:

```powershell
Start-Process http://127.0.0.1:8787/
```

O atalho existente `operar_agente_vps.ps1` executa essas duas ações.

## Como o Codex 2 deve trabalhar

1. Ler este arquivo, `HANDOFF_PARA_OUTRA_IA.md`, `IMPLEMENTATION_STATUS.md` e o `git status`.
2. Fazer alterações no repositório, sem editar diretamente a release ativa no VPS.
3. Validar Python/JavaScript e testes focados.
4. Criar commit descritivo e publicar no repositório.
5. Publicar uma nova pasta em `/opt/agente-vendas-local/releases/`.
6. Validar a nova pasta antes de trocar `/opt/agente-vendas-local/app`.
7. Reiniciar somente os serviços necessários e confirmar `systemctl is-active`.

## Serviços remotos

- `agente-vendas-control`: painel RPC em loopback na porta 8787.
- `agente-vendas-worker`: ciclos do agente e fila de tarefas.
- `agente-vendas-internal-browser`: sessão persistente do navegador interno.
- `agente-vendas-diagnostics`: diagnóstico de memória, abas e recuperação.

Não registrar tokens, cookies, senhas ou conteúdo privado nos commits, relatórios ou logs.
