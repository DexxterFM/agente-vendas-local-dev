/* Ponte para o painel servido pela VPS através de um túnel SSH local. */
(() => {
  if (window.sales) return;
  // crypto.randomUUID não existe em WebViews antigos nem em contexto não
  // seguro; sem o fallback toda chamada RPC falhava antes de sair do navegador.
  const requestId = () => (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function')
    ? crypto.randomUUID()
    : 'rpc-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  const unsupported = (name) => async () => { throw new Error(`${name} está disponível no navegador interno do aplicativo Windows.`); };
  window.sales = {
    async call(command, args = {}) {
      const response = await fetch('/api/rpc', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:requestId(),command,args})});
      const body = await response.json().catch(() => ({ok:false,error:'Resposta inválida do agente.'}));
      if (!body.ok) throw new Error(body.error || 'Falha ao consultar o agente na VPS.');
      return body.result;
    },
    // O painel da VPS é sempre remoto; informar isso permite ao runtime abrir
    // direto a tela interna sem tentar o BrowserView nativo.
    remoteMode: async () => true,
    openExternal: async (url) => { window.open(url, '_blank', 'noopener'); },
    // Não existe BrowserView nativo neste modo: resolver (em vez de rejeitar)
    // evita promessas não tratadas e telas presas no botão do navegador.
    browserPane: async () => ({ open: false, url: '' }),
    browserObserve: unsupported('A leitura da tela do Instagram'),
    browserSend: unsupported('O envio pelo navegador interno'),
    importBrowserInbox: unsupported('A importação pelo navegador interno'),
    scanFeedProfiles: unsupported('A prospecção visual'),
  };
})();
