/* O módulo é renderizado por runtime.js; este arquivo apenas registra o item de navegação. */
(()=>{
  const nav=document.querySelector('.nav-list');
  if(!nav||nav.querySelector('[data-view="research"]'))return;
  const button=document.createElement('button');
  button.className='nav-item';
  button.dataset.view='research';
  button.innerHTML='<span>◈</span> Pesquisa e aprendizado';
  // `window.moduleView?.('research').catch(...)` quebrava silenciosamente: a
  // chamada opcional curto-circuita a cadeia inteira, então o item do menu não
  // abria nada quando o runtime ainda não tinha exposto a função.
  button.addEventListener('click',()=>{
    const view=window.moduleView;
    if(typeof view!=='function')return;
    Promise.resolve(view('research')).catch(window.report||(()=>{}));
  });
  nav.appendChild(button);
})();
