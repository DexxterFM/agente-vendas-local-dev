# Manual de produto e configuração

## Instalação

1. Execute `AgenteVendasLocal-Setup.exe`.
2. Abra **Agente de Vendas Local** pelo Menu Iniciar.
3. Em **Navegador interno**, entre na conta Instagram autorizada.
4. Em **Integração Instagram/Meta**, conclua a autorização Meta quando usar a API.
5. Em **Oferta 3 meses**, confira e salve os links oficiais de Clínica/equipe e Profissional individual.
6. Revise a **Biblioteca de respostas** e só então ative o agente.

## Configuração técnica

Copie `.env.example` para `.env`. Nunca versione dados reais. As variáveis
cobrem Ollama, Meta/Instagram, PostFlow e ERP Clínica TEA.

## Oferta de três meses

O módulo **Oferta 3 meses** mantém dois links HTTPS persistidos localmente:

- **Clínica/equipe:** encaminhado após o lead indicar clínica, equipe ou operação multiprofissional.
- **Profissional individual:** encaminhado após o lead indicar consultório ou atendimento individual.

O agente usa os links guardados nessa configuração ao montar a resposta. O
período começa após a ativação acompanhada.

## Dados locais

O CRM e a memória ficam no computador do operador. Não inclua banco SQLite,
logs, tokens, cookies ou arquivos `.env` em Git, instaladores ou backups públicos.
