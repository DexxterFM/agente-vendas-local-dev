# Estratégia de repositórios

`sales_agent_unified` é o repositório de desenvolvimento: integrações, testes
e evolução do produto acontecem aqui.

`agente-vendas-local-produto` é o repositório de entrega: recebe somente um
snapshot testado, documentação de operação, configuração de exemplo e o
processo de build. Não recebe bancos, logs, tokens, sessões, `node_modules`,
`dist` ou auditorias locais.

## Promoção

1. Testar no desenvolvimento.
2. Atualizar documentação e checklist de release.
3. Criar commit de release.
4. Copiar o snapshot para o produto e registrar a origem no changelog.
5. Gerar/testar o instalador no repositório de produto.
6. Publicar no GitHub quando a autenticação estiver válida.
