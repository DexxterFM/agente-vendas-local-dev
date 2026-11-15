# Pesquisa e aprendizado comercial

O menu Pesquisa e aprendizado reúne:

- Pesquisas e livros: título, autor, fonte, método e resumo de aplicação; consulta RAG pelo contexto da conversa.
- Personalidade: tom, detalhe, saudação, perguntas, objeções e fechamento, com versões persistentes.
- Interações: lead, contexto, método, versão da personalidade e identificador da mensagem realmente enviada.
- Resultados: resposta e contratação confirmadas, separados de resultados desconhecidos.
- Probabilidades: estimativa Beta(1,1) por método e contexto, com tamanho da amostra. Não é uma previsão calibrada individual de cada frase nem prova causal de eficácia.
- Estratégias aprendidas: o contexto de geração recebe os resultados observados. Uma preferência por método só é persistida com pelo menos 20 resultados de resposta conhecidos; o registro permanece rastreável.
- Instalação: URL oficial HTTPS e passos que o agente consulta para orientar pelo chat. Não há link real pré-cadastrado nem preços de concorrentes inventados.

O aprendizado usa memória e recuperação documental; não altera os pesos do modelo. Resultados comerciais precisam ser registrados para alimentar estimativas. O registro automático dos resultados por webhook/CRM continua dependente da integração Meta.

Ao argumentar pela migração, o agente deve relacionar necessidades declaradas a funcionalidades e condições verificadas do ERP. Conhecimentos sobre concorrentes vêm dos comparativos documentados. Um livro ou método é referência de abordagem, não evidência de que uma mensagem específica funcionará.

Livros completos não estão incluídos. O espaço aceita referências, resumos e materiais fornecidos pelo operador. Todos os dados comerciais persistem no SQLite local; decisões técnicas do projeto também foram registradas no LÚMEN.
