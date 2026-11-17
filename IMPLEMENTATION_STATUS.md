# Estabilização e convites — registro de execução

## Base inspecionada em 17/11/2026
- Commit local: ec827ea.
- Release ativa VPS: release-20261117-flow-studio (mudou desde a investigação anterior).
- Alterações existentes preservadas: frontend/index.html, runtime.js, styles.css.
- Memória do serviço observada: 2.069.180.416 bytes; pico 2.376.171.520 bytes.
- Diagnóstico de página pronta não comprova saúde de memória nem conclusão de tarefa.

## Alteração preparada
- Diagnóstico mede RSS e swap por processo do serviço usando /proc, inclusive quando a página não responde; não coleta argumentos, mensagens ou credenciais.
- Publicado na release ativa; lock de tarefa e limpeza de páginas do centro de contas também estão ativos.
- Limite do navegador: máximo de 4 processos de renderização e um processo por site.
- Após a publicação: 1 página principal, memória atual medida pelo systemd em 685 MB, pico 834 MB.
- O worker agora adquire `browser-task.lock` antes de qualquer ciclo; DMs e prospecção aguardam a liberação.
- Páginas `accountscenter.instagram.com` antigas são fechadas antes do ciclo; o perfil autenticado permanece preservado.
- Teste dirigido: 4 casos de diagnóstico/compositor/oferta passaram.

## Próximos gates obrigatórios
0. Campanhas agora têm histórico por perfil, estados por interação e editor persistente da mensagem de prospecção.
1. Snapshot e hashes da release/configuração e pacote PC; baseline de memória. (parcial: baseline VPS registrado)
2. Reprodução controlada e identificação do crescimento; correção e teste.
3. Coordenador exclusivo entre processos e confirmação/deduplicação.
4. Automações completas e integração real dos dois geradores.
5. Testes de colisão, convites e estabilidade de duas horas; publicação identificada.

Não declarar conclusão antes de passar todos os gates.
