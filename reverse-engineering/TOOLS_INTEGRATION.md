# Ferramentas escolhidas e integração

## Fontes analisadas

- `browser-use-src/`: fonte do browser-use. A análise confirmou que ele é um
  runtime Python/CDP independente, com dependências próprias e múltiplas
  estratégias de navegador. Ele foi mantido como referência, não embutido no
  executável do CRM.
- `BrowserOS-src/`: fonte do BrowserOS neo. A documentação e o cliente de
  desenvolvimento confirmam MCP Streamable HTTP e o endpoint padrão local
  `http://127.0.0.1:9200/mcp`.
- `BrowserOS-src/skills/browseros-neo/SKILL.md`: contrato operacional usado para
  a integração: `run`, `snapshot`, `act`, `read` e ciclo snapshot → act → verify.

## O que foi integrado ao Agente de Vendas Local

Além do adaptador MCP, o Electron agora possui um painel Chromium interno
(`WebContentsView`) com perfil persistente próprio. O botão **Navegador interno**
abre o Instagram dentro da janela do CRM; a navegação é feita por IPC e aceita
somente URLs HTTPS. Isso evita abrir uma segunda janela e não depende de uma
sessão autenticada do PostFlow.

`adapters/browseros.py` agora expõe:

- `tools()` para descobrir as ferramentas reais oferecidas pelo servidor MCP;
- `snapshot(url)` para abrir uma página e obter a árvore de acessibilidade;
- `act(url, action)` para executar uma ação estruturada e devolver a leitura
  posterior da página;
- `run(code)` como transporte de rotinas curtas do BrowserOS;
- `open_instagram_inbox()` para o fluxo de teste do Instagram.

Os comandos desktop correspondentes são `browserTools`, `browserSnapshot` e
`browserAct`. Eles foram incluídos na lista IPC permitida do Electron.

## Limite verificável

Os testes locais validam o cliente MCP, o RPC e a sintaxe do Electron. A ação
real sobre mouse/teclado, abas autenticadas e clipboard só pode ser validada
quando o BrowserOS neo estiver executando e conectado ao endpoint MCP. O
aplicativo não copia cookies nem cria uma sessão paralela.

## Comando de uso

Configure, se necessário, no `.env` do projeto:

```text
BROWSEROS_MCP_URL=http://127.0.0.1:9200/mcp
```

Depois use `browserTools` para descobrir os nomes/esquemas atuais e sempre
execute `browserSnapshot` antes de `browserAct`. Assim o agente trabalha pelos
refs atuais da árvore de acessibilidade e verifica o resultado após cada ação.
