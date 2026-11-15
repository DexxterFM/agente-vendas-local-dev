# Memória comercial e histórico

O importador lê as conversas disponibilizadas pela Graph API e preserva ID externo, conta, direção e data original. Importações repetidas não duplicam mensagens. A cobertura permanece `api_partial`: os dados retornados pela Meta não representam necessariamente todo o passado da conta. Novos eventos devem passar pelo mesmo mecanismo de deduplicação.

O CRM classifica as mensagens recebidas, sem atribuir ao cliente a intenção escrita pelo vendedor. As análises contam mensagens enviadas, retornos seguintes e tempo mediano até o retorno. São observações, não provas de conversão. Tempo economizado não é calculado sem referência manual. Vendas efetivas precisam de um evento de contratação confirmado.

A documentoteca guarda fonte, categoria, versão por hash e data de atualização. Documentos são divididos em trechos e recuperados por busca lexical local antes da geração no Ollama. Categorias: produto, comparativo, roteiro e documentação do projeto. Documentação técnica não entra automaticamente nas respostas comerciais.

A trilha considera o histórico recente: descoberta, comparação documentada, proposta e encerramento. Métricas agregadas ajudam o modelo a escolher a abordagem, sem copiar conversas identificáveis de outros clientes. Não é ajuste de pesos do modelo.

Comparativos contêm nome e plano de cada produto, funcionalidades, preços com moeda e periodicidade, fonte e data de verificação. O gerador `comparison` cria um pôster HTML em `comparativos/` e indexa os fatos na documentoteca. A revisão periódica dos preços depende de novas fontes fornecidas. Não há tabela real de concorrentes inventada ou pré-carregada.

Importar documentos previamente produzidos requer selecionar o material comercial correto. Não indexar indiscriminadamente toda a pasta do projeto: ela contém relatórios técnicos e pode conter credenciais. Não há importação automática de outros projetos ou da memória LÚMEN deles.
