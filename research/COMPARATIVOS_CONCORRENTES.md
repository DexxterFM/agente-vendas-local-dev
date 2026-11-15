# Biblioteca de comparativos do agente

Atualização factual: **14/11/2026**.

O arquivo operacional detalhado é `competitor_catalog.json`. Ele contém, para cada concorrente:

- nomes e aliases reconhecidos nas DMs;
- posicionamento, preço público e funcionalidades encontradas nas páginas oficiais;
- vantagens documentadas do ERP Clínica TEA;
- dossiê comercial para o RAG;
- perguntas de descoberta e respostas a objeções;
- fontes oficiais e data de consulta;
- prompt factual para gerar um pôster 1080 × 1350;
- caminho esperado da imagem gerada.

## Concorrentes cobertos

1. iClinic
2. Clínica Ágil
3. Feegow Clinic
4. Amplimed
5. Ninsaúde Clinic
6. Clínica nas Nuvens
7. GestãoDS
8. Shosp
9. ProDoctor
10. HiDoctor
11. Doctoralia Pro
12. Conclínica

Esta é uma lista dos principais concorrentes brasileiros com oferta pública localizada, não uma alegação de exaustividade permanente. O mercado deve ser revisado trimestralmente.

## Como gerar e instalar os pôsteres

1. Abra `research/competitor_catalog.json`.
2. Copie o campo `poster_prompt` do concorrente desejado para o gerador de imagens.
3. Exporte exatamente em PNG, 1080 × 1350.
4. Salve usando o caminho do campo `asset.path`, por exemplo `assets/comparativos/iclinic.png`.
5. Execute a validação. O agente passa a devolver `asset_ready: true` e associa a imagem à DM que mencionar aquele concorrente.

## Regras comerciais armazenadas

- A comparação é consultiva: reconhecer os pontos fortes do sistema atual e investigar o fluxo real.
- Preço de entrada nunca representa automaticamente o custo total; verificar profissionais, plano, adicionais e período promocional.
- “Não localizado na página consultada” não significa “o concorrente não possui”.
- O ERP Clínica TEA deve ser defendido por fatos documentados: foco TEA/ABA, prontuário multidisciplinar, metas, perfil sensorial, supervisão, portal familiar e operação integrada.
- Se a clínica não usa aplicativo, Denis elogia a iniciativa de organização, apresenta benefícios relevantes e faz uma pergunta de descoberta.
- Denis é de Porto Alegre/RS, mantém tom experiente e simpático e usa apenas emojis positivos com moderação: 😊 👏 👍 ❤️.
- Uma objeção abre investigação; somente um pedido claro para interromper contato encerra a conversa.

