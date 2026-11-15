/* Ponte para o painel servido pela VPS através de um túnel SSH local. */
(() => {
  if (window.sales) return;
  const unsupported = (name) => async () => { throw new Error(`${name} está disponível no navegador interno do aplicativo Windows.`); };
  window.sales = {
    async call(command, args = {}) {
      const response = await fetch('/api/rpc', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:crypto.randomUUID(),command,args})});
      const body = await response.json();
      if (!body.ok) throw new Error(body.error || 'Falha ao consultar o agente na VPS.');
      return body.result;
    },
    openExternal: async (url) => { window.open(url, '_blank', 'noopener'); },
    browserPane: unsupported('O navegador interno'),
    browserObserve: unsupported('A leitura da tela do Instagram'),
    browserSend: unsupported('O envio pelo navegador interno'),
    importBrowserInbox: unsupported('A importação pelo navegador interno'),
    scanFeedProfiles: unsupported('A prospecção visual'),
  };
})();
