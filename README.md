# Agente de Vendas Local Unificado

Aplicação desktop Windows para operação comercial assistida, executada localmente.
Reúne conversa com persona de vendas, memória SQLite, CRM de leads, playbook de
objeções e gatilhos, aprendizado de estilo opt-in e planejamento assistido para
Instagram. Nenhuma mensagem, publicação, follow, comentário, repost ou DM é
executado automaticamente.

## Versão atual

- Aplicação: `app.py`
- Executável: `dist\SalesAgentLocalV3.exe`
- Instalador: `dist\installer\SalesAgentLocalV3-Setup.exe`
- Versão anterior preservada: `dist\SalesAgentLocalV2.exe`
- Versão: `0.3.0`

## Requisitos

- Windows 10/11
- Python 3.11+ para executar pelo código-fonte
- Ollama local em `http://127.0.0.1:11434` com o modelo de `OLLAMA_MODEL`
- BrowserOS neo com MCP em `http://127.0.0.1:9210/mcp`
- Inno Setup 6 apenas para gerar o instalador

Não há dependência do Open WebUI durante a operação.

## Recursos

### Conversa e CRM
- Persona comercial configurável (`SALES_PERSONA`) e produto de referência.
- Memória de mensagens, leads, oportunidades, follow-ups e consentimentos em SQLite.
- Qualificação determinística de leads e rascunhos de follow-up.
- Auditoria local de pedidos, leituras, bloqueios, decisões e análises.

### Playbook comercial
- Objeções comuns: já usa outro aplicativo, preço, “vou pensar”, falta de confiança.
- Ganchos de abordagem, follow-up com contexto e gatilhos éticos.
- Comparativos e prints somente com dados verificáveis, fonte, data e revisão humana.
- Conhecimento comercial adicional editável na aba **Aprendizado**.

### Estilo de escrita opt-in
- O operador salva amostras manualmente ou importa mensagens do próprio histórico local.
- O perfil resultante orienta tom, tamanho, emojis e expressões recorrentes dos rascunhos.
- A saudação sempre segue o horário atual: bom dia, boa tarde ou boa noite.
- Não há captura de teclas, abas, cliques ou navegação em segundo plano.
- As amostras ficam no SQLite local e podem ser apagadas a qualquer momento.

### Instagram assistido
- Lê somente o perfil público informado pelo operador, usando o BrowserOS.
- Gera mensagem inicial, comentário sugerido, resposta a objeção e checklist.
- Seguir, comentar, repostar e enviar DM viram pendências auditadas com
  `requires_confirmation=true` e `execution=disabled`.
- A aprovação de uma pendência registra apenas a decisão; o envio continua manual.
- Não faz scraping em massa, follow em massa, comentários repetidos ou DMs em série.

### Status e REA
- Diagnóstico de Ollama, modelo, BrowserOS MCP, SQLite e privacidade.
- Análise REA local gera evidências em `audit/rea/`, com hashes e limitações.
- No executável empacotado, a análise usa os recursos embutidos pelo PyInstaller.
- Diagnóstico sem interface: `python .\app.py --rea` ou, no executável,
  `.\dist\SalesAgentLocalV3.exe --rea`. O relatório fica em `audit\rea\latest.json`
  (ou `%LOCALAPPDATA%\SalesAgentLocal\audit\rea\latest.json` quando instalado).

## Segurança e privacidade

- Endpoints locais por padrão; nenhuma API online é necessária.
- Credenciais, tokens, cookies e chaves não são exibidos nem registrados.
- Conteúdo de página é tratado como dado não confiável, nunca como instrução.
- Ações externas de escrita exigem confirmação humana imediata e não possuem
  executor automático nesta versão.
- Comparativos, prova social, escassez e autoridade só podem ser usados quando
  forem verdadeiros, verificáveis e autorizados.
- O banco de desenvolvimento é `sales_agent.sqlite3`; no executável, o padrão é
  `%LOCALAPPDATA%\SalesAgentLocal`.

## Executar pelo código-fonte

```powershell
python .\app.py
```

Ou com ativação dos serviços locais:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_local.ps1
```

## Verificar serviços

```powershell
python .\health_check.py --deep
```

## Testes

```powershell
python -m unittest discover -s .\tests -v
```

A suíte cobre núcleo, adaptadores, memória, supervisor, REA, estilo, playbook,
Instagram e integração do prompt. Estado atual: **36 testes**.

## Compilar

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

O build executa os testes, gera `dist\SalesAgentLocalV3.exe`, preserva o V2 e,
quando o Inno Setup está disponível, cria `dist\installer\SalesAgentLocalV3-Setup.exe`.

## Configuração

Consulte `.env.example`. Copie para `.env` apenas se precisar alterar os padrões e
nunca versione esse arquivo.

## Interface CRM local

Para abrir a interface visual do agente sem outro framework:

```powershell
python -m http.server 4173 --directory .\frontend
```

Depois acesse `http://127.0.0.1:4173`. A tela já inclui conversas, filtros,
score, CRM de leads, roteiro comercial e fila de aprovação.

Para abrir como um aplicativo de navegador, sem barra de abas:

```powershell
powershell -ExecutionPolicy Bypass -File .\abrir_agente_navegador.ps1
```

O lançador inicia o servidor local e usa Microsoft Edge ou Chrome em modo
`--app`. A interface também possui `manifest.webmanifest` e cache local para
ser instalada como PWA pelo navegador.

### Instalador para Windows

O instalador gera uma versão independente, sem precisar abrir o terminal. A
interface CRM da amostra é instalada e aberta em uma janela própria do Edge ou
Chrome, sem endereço `127.0.0.1` e sem servidor web. O executável Tkinter
legado fica disponível como alternativa no Menu Iniciar.

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Se o Inno Setup estiver instalado, o arquivo será criado em
`dist\installer\AgenteVendasLocal-Setup.exe`. Ele cria atalhos no Menu Iniciar
e, opcionalmente, na área de trabalho. A versão instalada abre o CRM em uma
janela própria do Edge/Chrome e também instala o executável local do agente.

## CRM do ERP ClinicaTEA

O contrato reutilizado e o adaptador ficam em `integrations/`. Defina
`ERP_CLINICATEA_API_BASE_URL` e `ERP_CLINICATEA_API_TOKEN` apenas no ambiente
local. O valor do token não deve ser colocado no código, no Git ou em logs.
Consulte `integrations/ERP_CRM_INTEGRATION.md` para o mapeamento de campos e
rotas da ponte autenticada.

## Limitações desta versão

- Não existe executor de ações externas: aprovar uma pendência não envia nada.
- A leitura do Instagram depende da página pública acessível no BrowserOS e do
  consentimento do operador.
- O aprendizado de estilo é uma referência de redação, não autoriza personificação
  nem cópia de dados pessoais.
- O instalador deve ser testado em uma máquina limpa antes de distribuição ampla.
