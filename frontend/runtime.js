/* Painéis operacionais da versão desktop. Nenhum módulo exibe JSON bruto. */
let selectedLead=null;
const el=s=>document.querySelector(s);
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const stageNames={acolhimento:'Acolhimento',descoberta:'Descoberta',qualificação:'Qualificação',apresentação:'Apresentação',objeção:'Objeção',proposta:'Proposta','follow-up':'Follow-up'};
async function call(command,args={}){if(!window.sales)throw Error('Abra a versão desktop instalada.');return window.sales.call(command,args);}
function report(error){const toast=el('#toast');toast.textContent=error.message||String(error);toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),4500);}
function activatePanel(title,subtitle='Central comercial conectada à memória local.'){
 const panel=el('#view-placeholder');el('#view-conversations').classList.remove('active-view');panel.classList.add('active');
 el('#page-title').textContent=title;panel.innerHTML=`<div class="module-heading"><div><p class="eyebrow">MÓDULO DO AGENTE</p><h2>${safe(title)}</h2><p>${safe(subtitle)}</p></div><span class="module-pulse">● Dados locais</span></div><div id="module-content" class="module-content"></div>`;
 return el('#module-content');
}
function button(label,kind='ghost-button',id=''){return `<button ${id?`id="${id}"`:''} class="${kind}">${label}</button>`;}
function empty(icon,title,detail){return `<div class="module-empty"><span>${icon}</span><h3>${safe(title)}</h3><p>${safe(detail)}</p></div>`;}
function formatTime(value){if(!value)return 'Agora';const d=new Date(value);return Number.isNaN(d)?safe(value):d.toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'});}

async function refreshSystemSummary(){
 const health=await call('status');
 const model=health.model||{};const postflow=health.postflow||{};const erp=health.erp||{};
 const modelText=el('#model-status-text');if(modelText)modelText.textContent=`Ollama · ${model.detail||'indisponível'}`;
 const modelDot=el('#model-status-dot');if(modelDot)modelDot.className=model.status==='connected'?'':'attention';
 const postflowThreads=Number(postflow.meta?.threads||0);const postflowText=el('#postflow-status-text');if(postflowText)postflowText.textContent=postflow.status==='connected'?`PostFlow conectado · ${postflowThreads} DMs`:'PostFlow requer atenção';
 const postflowIcon=el('#postflow-status-icon');if(postflowIcon)postflowIcon.textContent=postflow.status==='connected'?'✓':'!';
 const postflowCard=el('#postflow-status-card');if(postflowCard)postflowCard.classList.toggle('attention',postflow.status!=='connected');
 const live=el('#live-data-label');if(live)live.textContent=`ERP ${erp.status==='connected'?'online':'atenção'} · PostFlow ${postflow.status==='connected'?'online':'atenção'}`;
 const alert=el('#connection-alert');if(alert){const healthy=erp.status==='connected'&&postflow.status==='connected'&&model.status==='connected';alert.classList.toggle('healthy',healthy);alert.innerHTML=healthy?'<strong>✓ Serviços comerciais conectados</strong><p>ERP Clínica TEA, PostFlow e modelo local estão disponíveis.</p>':`<strong>⚠ Serviço requer atenção</strong><p>${safe([erp,postflow,model].filter(item=>item.status!=='connected').map(item=>item.label||item.detail).join(' · ')||'Atualize o status para tentar novamente.')}</p>`;}
 return health;
}

function renderEmptyConversation(){
 selectedLead=null;
 el('#chat-company').textContent='Nenhuma conversa importada';
 el('#chat-handle').textContent='Abra o Instagram no navegador interno para começar';
 el('#chat-body').innerHTML='<p class="empty-chat">As conversas reais aparecerão aqui após a importação das DMs.</p>';
 el('#draft-text').textContent='Selecione uma conversa para gerar uma resposta contextual.';
 el('.hot-badge').textContent='◌ Aguardando conversas';
 el('#profile-company').textContent='Memória comercial';
 el('.profile-head span').textContent='Sem perfil selecionado';
 el('.profile-facts').innerHTML='<div><dt>Status</dt><dd>Sem dados importados</dd></div><div><dt>Próximo passo</dt><dd>Importar DMs do Instagram</dd></div>';
 el('.score-block strong').textContent='0 / 100';
 el('.score-bar i').style.width='0%';
 el('.contact-meta').textContent='Aguardando sincronização';
}

async function vpsInternalBrowserView(){
 const content=activatePanel('Navegador interno do agente','Sessão persistente do agente na VPS. A entrada é feita uma única vez e permanece no servidor.');
 content.innerHTML=`<section class="data-card" style="max-width:1280px"><div class="module-heading"><div><p class="eyebrow">SESSÃO REMOTA PERSISTENTE</p><h3 id="vps-browser-status">Conectando…</h3></div><div class="editor-actions"><button class="ghost-button" id="vps-browser-back" title="Voltar">← Voltar</button><button class="ghost-button" id="vps-browser-forward" title="Avançar">Avançar →</button><button class="ghost-button" id="vps-browser-home" title="Abrir início">⌂ Início</button><button class="ghost-button" id="vps-browser-confirm" title="Confirmar perfil salvo">✓ Confirmar perfil</button><button class="ghost-button" id="vps-browser-relogin" title="Abrir a tela de login">↻ Relogar</button><button class="ghost-button" id="vps-browser-refresh">↻ Atualizar imagem</button><button class="ghost-button" id="vps-browser-enter">↵ Enter</button></div></div><div id="vps-browser-layout" style="display:grid;grid-template-columns:minmax(0,1fr) 250px;gap:14px"><div id="vps-browser-stage" tabindex="0" role="application" aria-label="Sessão interna interativa" style="position:relative;background:#07111f;border:1px solid #203a56;border-radius:12px;overflow:auto;min-height:520px;outline:none"><img id="vps-browser-screen" alt="Tela do navegador interno remoto" style="display:block;width:100%;min-width:760px;cursor:text;pointer-events:none" /></div><form id="vps-browser-input" class="dialog-form" style="margin:0"><label style="display:grid;gap:5px;color:#9fb2c6;font-size:10px">Janela exibida<select id="vps-browser-target" style="width:100%;padding:8px;border:1px solid #29445f;border-radius:8px;background:#071624;color:#eff6ff;font-size:11px"></select></label><label>Texto para o campo selecionado<textarea name="text" rows="5" placeholder="Clique em um campo na tela e digite aqui."></textarea><small>O texto é encaminhado somente para a sessão interna do agente.</small></label><button class="primary-button" type="submit">Digitar</button><button class="ghost-button" type="button" id="vps-browser-tab">Tab</button><p style="font-size:11px;color:#8fa4ba;line-height:1.45">Clique no campo na tela e use o teclado normalmente. Enter, Tab, Backspace, Delete e setas também funcionam.</p></form><details style="grid-column:1/-1;font-size:11px;color:#9fb2c6"><summary>Importar sessão de outro navegador (recuperação de bloqueio)</summary><p>Se o Instagram bloqueou o IP da VPS, exporte os cookies de um navegador onde a conta esteja logada e cole o JSON abaixo. Isso restaura a sessão sem novo login.</p><textarea id="vps-browser-cookies" rows="4" placeholder='[{"name":"cookie_name","value":"...","domain":".instagram.com","path":"/","secure":true}]'></textarea><button class="ghost-button" type="button" id="vps-browser-import">Importar cookies</button></details></div></section>`;
 const layout=el('#vps-browser-layout'),stage=el('#vps-browser-stage'),screen=el('#vps-browser-screen'),inputForm=el('#vps-browser-input');const status=el('#vps-browser-status');
 screen.style.width='100%';screen.style.maxWidth='1280px';screen.style.height='auto';screen.style.objectFit='contain';screen.style.margin='0 auto';
 let refreshing=false;
 const refresh=async()=>{if(refreshing||!document.body.contains(screen))return;refreshing=true;try{const state=await call('internalBrowserStatus');layout.style.gridTemplateColumns='minmax(0,1fr) 250px';inputForm.hidden=false;stage.style.minHeight='520px';screen.style.minWidth='760px';if(!state.running){status.textContent='Navegador interno indisponível';return;}const visual=await call('internalBrowserVisualState').catch(()=>({ready:false,authenticated_surface:false}));const image=await call('internalBrowserScreenshot').catch(()=>null);let selected=null;try{const list=await call('internalBrowserTargets');const options=(list.targets||[]).map(t=>`<option value="${safe(t.id)}" ${t.selected?'selected':''}>${safe(t.title||'Janela')} · ${safe(t.url||'')}${t.verification?' · verificação':''}</option>`).join('');const picker=el('#vps-browser-target');if(picker&&picker.innerHTML!==options)picker.innerHTML=options;selected=(list.targets||[]).find(t=>t.selected)||null;}catch(error){}let ls={};try{ls=await call('internalBrowserLoginState');}catch(error){}const urlPart=selected&&selected.url?' · '+String(selected.url).replace(/^https?:\/\//,''):'';const RATE='⚠ Instagram bloqueou este IP (HTTP 429). Aguarde 15–30 min ou troque a rede/IP da VPS; senha correta não resolve.';const stateMsg={authenticated:'Sessão interna ativa',rate_limited:RATE,challenge:'Digite o código de confirmação (SMS) enviado pelo Instagram.',login_form:'Tela de login: digite usuário e senha; se pedir código, use o campo de texto.',profile_confirmation:'Sessão salva encontrada: clique em ✓ Confirmar perfil para entrar.',unknown:''};status.textContent=(stateMsg[ls.state]||(visual.authenticated_surface?'Sessão interna ativa':(visual.ready?'Conclua a entrada na sessão interna':'Ação em andamento · exibindo a tela atual')))+urlPart;if(ls.state==='rate_limited')status.style.color='#ff8f6b';else status.style.color='';if(!image?.png||Number(image.width)<200||Number(image.height)<200){if(!screen.dataset.stableFrame)status.textContent='Aguardando a imagem da sessão interna';return;}screen.dataset.remoteWidth=String(Number(image.width)||1280);screen.dataset.remoteHeight=String(Number(image.height)||900);screen.src='data:image/png;base64,'+image.png;screen.dataset.stableFrame='true';}finally{refreshing=false;}};
 const action=async payload=>{await call('internalBrowserAction',payload);await new Promise(resolve=>setTimeout(resolve,650));await refresh();};
 let keyQueue=Promise.resolve(),keyRefresh=null;
 const queueKey=payload=>{keyQueue=keyQueue.then(()=>call('internalBrowserAction',payload)).then(()=>{clearTimeout(keyRefresh);keyRefresh=setTimeout(()=>refresh().catch(()=>null),180);}).catch(report);};
 let lastPointer=0;
 const forwardPointer=event=>{const rect=screen.getBoundingClientRect(),width=Number(screen.dataset.remoteWidth)||1280,height=Number(screen.dataset.remoteHeight)||900;stage.focus({preventScroll:true});status.textContent='Enviando clique para a sessão interna…';action({kind:'click',x:Math.round((event.clientX-rect.left)*width/rect.width),y:Math.round((event.clientY-rect.top)*height/(rect.height||1))}).catch(report);};
 stage.onpointerdown=event=>{lastPointer=Date.now();event.preventDefault();forwardPointer(event);};
 stage.onclick=event=>{if(Date.now()-lastPointer>250)forwardPointer(event);};
 stage.onkeydown=event=>{if(event.ctrlKey||event.metaKey||event.altKey)return;const special=new Set(['Enter','Tab','Escape','Backspace','Delete','ArrowLeft','ArrowUp','ArrowRight','ArrowDown']);if(event.key.length===1){event.preventDefault();queueKey({kind:'type',text:event.key});return;}if(special.has(event.key)){event.preventDefault();queueKey({kind:'key',key:event.key});}};
 el('#vps-browser-input').onsubmit=event=>{event.preventDefault();const text=new FormData(event.target).get('text');if(!String(text||'').trim())return;action({kind:'type',text:String(text)}).then(()=>event.target.reset()).catch(report);};
 el('#vps-browser-refresh').onclick=()=>refresh().catch(report);el('#vps-browser-back').onclick=()=>action({kind:'back'}).catch(report);el('#vps-browser-forward').onclick=()=>action({kind:'forward'}).catch(report);el('#vps-browser-home').onclick=()=>action({kind:'navigate',url:'https://www.instagram.com/'}).catch(report);el('#vps-browser-enter').onclick=()=>action({kind:'key',key:'Enter'}).catch(report);el('#vps-browser-tab').onclick=()=>action({kind:'key',key:'Tab'}).catch(report);const targetPicker=el('#vps-browser-target');if(targetPicker)targetPicker.onchange=()=>call('internalBrowserSelectTarget',{id:targetPicker.value}).then(()=>refresh()).catch(report);el('#vps-browser-confirm').onclick=()=>call('internalBrowserAction',{kind:'confirm_profile'}).then(r=>{if(r&&r.clicked===false)report('Nenhum botão de confirmação visível nesta janela.');return refresh();}).catch(report);el('#vps-browser-import').onclick=()=>{let cookies;try{cookies=JSON.parse(el('#vps-browser-cookies').value);}catch(e){report('JSON de cookies inválido.');return;}call('internalBrowserImportSession',{cookies:cookies}).then(r=>{report({message:'Sessão importada: '+String((r&&r.imported)||0)+' cookies.'});return refresh();}).catch(report);};el('#vps-browser-relogin').onclick=()=>action({kind:'navigate',url:'https://www.instagram.com/accounts/login/'}).catch(report);await refresh();
 const liveImage=setInterval(()=>{if(!document.body.contains(screen)){clearInterval(liveImage);return;}refresh().catch(()=>null);},1500);
}
function bindBrowserControls(){
 let browserVisible=true;
 const browserButton=el('#browser-pane-btn');
 const toolbar=el('#browser-toolbar');
 const updateBrowserToggle=()=>{if(!browserButton)return;browserButton.textContent=browserVisible?'▣ Ocultar navegador':'🌐 Mostrar navegador';browserButton.setAttribute('aria-pressed',String(browserVisible));};
 updateBrowserToggle();
 window.sales.remoteMode?.().then(remote=>{if(remote){browserVisible=false;toolbar.hidden=true;updateBrowserToggle();}}).catch(()=>null);
 // O BrowserView é uma camada nativa acima do painel. Este alternador mantém
 // o navegador como ferramenta principal, mas libera o CRM e o importador de
 // DMs sem o operador precisar fechar o aplicativo.
 browserButton?.addEventListener('click',async()=>{
   try{const remote=await call('internalBrowserStatus');if(remote?.running){await window.sales.browserPane('hide').catch(()=>null);browserVisible=false;toolbar.hidden=true;updateBrowserToggle();await vpsInternalBrowserView();return;}}catch{}
   if(browserVisible){await window.sales.browserPane('hide');browserVisible=false;toolbar.hidden=true;updateBrowserToggle();report({message:'Painel comercial exibido.'});return;}
   const result=await window.sales.browserPane('open');
   if(result?.open){browserVisible=true;toolbar.hidden=false;el('#browser-address').value=result.url||el('#browser-address').value;updateBrowserToggle();report({message:'Navegador interno exibido.'});}
 });
 document.querySelectorAll('[data-browser-action]').forEach(button=>button.addEventListener('click',async()=>{const result=await window.sales.browserPane(button.dataset.browserAction);if(button.dataset.browserAction==='hide'||button.dataset.browserAction==='close'){browserVisible=false;toolbar.hidden=true;updateBrowserToggle();}else if(result?.url){browserVisible=true;toolbar.hidden=false;updateBrowserToggle();el('#browser-address').value=result.url;}}));
 el('#browser-go')?.addEventListener('click',async()=>{const result=await window.sales.browserPane('navigate',el('#browser-address').value);if(result?.url)el('#browser-address').value=result.url;});
 el('#browser-address')?.addEventListener('keydown',event=>{if(event.key==='Enter')el('#browser-go')?.click();});
 el('#edit-btn')?.addEventListener('click',()=>{const draft=el('#draft-text');draft.contentEditable=String(draft.contentEditable!=='true');draft.focus();});
 el('#copy-btn')?.addEventListener('click',async()=>{await navigator.clipboard.writeText(el('#draft-text').textContent||'');report({message:'Rascunho copiado.'});});
}

async function refreshLeads(){
 const leads=await call('leads');const list=el('.conversation-list');if(!list)return;
 list.innerHTML='<div class="inbox-import-actions"><button class="primary-button" id="import-browser-dms">↻ Importar DMs do Instagram</button><button class="ghost-button" id="new-lead">+ Novo lead</button></div>'+leads.map(l=>`<button class="conversation-item" data-lead-id="${l.id}"><span class="company-avatar">${safe((l.name||'?')[0])}</span><span class="conversation-copy"><strong>${safe(l.name)}</strong><small>${safe(l.contact||'Sem contato')}</small><em class="status-pill">${safe(l.stage||'Novo')}</em></span><time>${safe(String(l.score||0))}</time></button>`).join('')||empty('◌','Ainda não há leads','Abra o navegador interno, entre no Instagram e importe as DMs existentes.');
 el('#lead-table').innerHTML=leads.map(l=>`<tr data-lead-id="${l.id}"><td><strong>${safe(l.name)}</strong></td><td>${safe(l.contact)}</td><td>—</td><td><span class="status-pill">${safe(l.stage)}</span></td><td><b class="score">${safe(l.score)}</b></td><td>${formatTime(l.updated_at)}</td><td>${safe(l.next_action||'—')}</td></tr>`).join('');
 document.querySelectorAll('[data-lead-id]').forEach(node=>node.onclick=()=>selectLead(Number(node.dataset.leadId)).catch(report));
 el('#new-lead').onclick=async()=>{const name=prompt('Nome da empresa ou contato');if(!name)return;const contact=prompt('Instagram ou contato')||'';await call('create',{name,contact});await refreshLeads();};
 el('#import-browser-dms').onclick=async()=>{const action=el('#import-browser-dms');action.disabled=true;action.textContent='Importando DMs…';try{const result=await window.sales.importBrowserInbox();await refreshLeads();report({message:`${result.threads} conversas do Instagram importadas; ${result.messages} mensagens novas e ${result.classified||0} leads classificados na memória.`});}finally{const current=el('#import-browser-dms');if(current){current.disabled=false;current.textContent='↻ Importar DMs do Instagram';}}};
 const warm=leads.filter(l=>String(l.stage||'').toLowerCase()==='warm');const hot=leads.filter(l=>String(l.stage||'').toLowerCase()==='hot');
 const counters={'#filter-all-count':leads.length,'#filter-answered-count':warm.length+hot.length,'#filter-waiting-count':leads.filter(l=>String(l.stage||'').toLowerCase()==='new').length,'#filter-qualified-count':hot.length,'#filter-followup-count':0};Object.entries(counters).forEach(([selector,value])=>{const node=el(selector);if(node)node.textContent=String(value);});
 const cards=document.querySelectorAll('.metrics-row article');const values=[leads.filter(l=>String(l.stage||'').toLowerCase()==='new').length,leads.length,hot.length,warm.length,0];cards.forEach((c,i)=>{if(i<5){c.querySelector('strong').textContent=values[i];c.querySelector('em').textContent='Memória comercial';}});
 if(!leads.length)renderEmptyConversation();
 else if(!selectedLead||!leads.some(lead=>lead.id===selectedLead.id))await selectLead(leads[0].id);
}
async function selectLead(id){
 const leads=await call('leads');selectedLead=leads.find(l=>l.id===id);if(!selectedLead)return;
 el('#chat-company').textContent=selectedLead.name;el('#chat-handle').textContent=selectedLead.contact||'Contato local';el('#profile-company').textContent=selectedLead.name;
 el('.hot-badge').textContent=`${Number(selectedLead.score)>=75?'🔥 Lead quente':'◈ Em desenvolvimento'} · score ${selectedLead.score}`;
 el('.profile-head span').textContent=selectedLead.contact||'Sem Instagram';el('.profile-facts').innerHTML=`<div><dt>Etapa atual</dt><dd>${safe(selectedLead.stage||'Novo')}</dd></div><div><dt>Observações</dt><dd>${safe(selectedLead.notes||'Sem observações')}</dd></div><div><dt>Próxima ação</dt><dd>${safe(selectedLead.next_action||'Definir próximo passo')}</dd></div>`;
 el('.score-bar i').style.width=Math.min(100,Number(selectedLead.score)||0)+'%';el('.score-block strong').textContent=`${selectedLead.score} / 100`;el('.contact-meta').textContent='Atualizado em '+formatTime(selectedLead.updated_at);
 const rows=await call('messages',{id});
 const body=el('#chat-body');
 body.innerHTML=rows.map((r,index)=>`<div class="bubble ${r[0]==='assistant'?'out':'in'}" data-bubble="${index}"><span class="bubble-text">${safe(r[1])}</span><time>${safe(r[2])}</time>${r[0]==='assistant'?`<button class="bubble-adjust" data-adjust="${index}" title="Editar e salvar esta resposta no fluxo">✎ Ajustar</button>`:''}</div>`).join('')||'<p>Sem mensagens registradas nesta conversa.</p>';
 body.querySelectorAll('[data-adjust]').forEach(button=>button.onclick=()=>openBubbleAdjust(Number(button.dataset.adjust),rows).catch(report));
 el('#draft-text').textContent='Clique em Gerar resposta para usar o contexto desta conversa.';
}
async function openBubbleAdjust(index,rows){
 const bubble=el(`[data-bubble="${index}"]`);
 if(!bubble)return;
 const trigger=[...rows.slice(0,index)].reverse().find(r=>r[0]==='user');
 if(!trigger)return report({message:'Não há mensagem do cliente antes desta resposta para vincular o ajuste.'});
 el('#chat-body').querySelectorAll('.bubble-editor').forEach(node=>node.remove());
 const editor=document.createElement('div');
 editor.className='bubble-editor';
 editor.innerHTML=`<small>O lead disse</small><blockquote>${safe(trigger[1])}</blockquote><label>Resposta que o agente deve enviar<textarea rows="4">${safe(rows[index][1])}</textarea></label><div class="bubble-editor-actions"><button class="primary-button" data-save>✓ Salvar resposta</button><button class="ghost-button" data-retest>↻ Perguntar de novo</button><button class="ghost-button" data-close>Cancelar</button></div><p class="bubble-test-result" hidden></p>`;
 bubble.insertAdjacentElement('afterend',editor);
 const field=editor.querySelector('textarea');
 const result=editor.querySelector('.bubble-test-result');
 const history=rows.slice(0,index).map(r=>({role:r[0],text:r[1]}));
 const ask=async()=>{
  result.hidden=false;result.textContent='Perguntando ao agente…';
  const answer=await call('draft',{id:selectedLead.id,browser_history:history});
  result.innerHTML=`<strong>Teste · mesma pergunta</strong><span>${safe(answer)}</span>`;
  return answer;
 };
 editor.querySelector('[data-retest]').onclick=()=>ask().catch(report);
 editor.querySelector('[data-close]').onclick=()=>editor.remove();
 editor.querySelector('[data-save]').onclick=async()=>{
  const button=editor.querySelector('[data-save]');
  button.disabled=true;button.textContent='Salvando…';
  try{
   const saved=await call('flowTeach',{message:trigger[1],response:field.value,lead_id:selectedLead.id});
   if(!saved.applied){report({message:saved.reason||'Nada foi alterado.'});return;}
   bubble.querySelector('.bubble-text').textContent=saved.template.response;
   const answer=await ask();
   result.innerHTML=`<strong>Salvo na versão ${safe(saved.revision)} · aprendizado gravado</strong><span>${safe(answer)}</span>`;
   report({message:`Resposta ajustada e salva na versão ${saved.revision}.`});
  }finally{button.disabled=false;button.textContent='✓ Salvar resposta';}
 };
 field.focus();
}

function templateCard(t,selected=false){return `<button class="flow-card ${selected?'selected':''}" data-template-id="${safe(t.id)}"><span class="flow-stage">${safe(stageNames[t.stage]||t.stage)}</span><strong>${safe(t.question)}</strong><small>${safe(t.response)}</small><em>${t.links?'↗ Link anexado':''}${t.images?' ▧ Imagem anexada':''}</em></button>`;}
async function followIntroView(){
 const templates=await call('followIntroTemplates');
 const labels={'intro-follow-clinic':'Clínica ou equipe','intro-follow-professional':'Profissional individual','intro-follow-community':'Comunidade'};
 const content=activatePanel('Agradecimento por seguir','Edite as três frases do primeiro contato. A prospecção usa a frase conforme o perfil descoberto.');
 content.innerHTML=`<div class="library-layout"><aside class="flow-sidebar"><div class="flow-sidebar-head"><div><small>FLUXO DE PROSPECÇÃO</small><h3>Primeiro contato</h3></div></div><div id="intro-list" class="template-list">${templates.map((t,i)=>`<button class="flow-card ${i===0?'selected':''}" data-intro-id="${safe(t.id)}"><span class="flow-stage">${safe(labels[t.id]||t.question)}</span><strong>${safe(labels[t.id]||t.question)}</strong><small>${safe(t.response)}</small></button>`).join('')||empty('▱','Sem frases','As frases padrão aparecem aqui.')}</div></aside><section class="flow-editor"><div class="editor-title"><div><span class="eyebrow">EDITOR DE FRASES</span><h3 id="intro-name">Selecione uma frase</h3></div><span class="save-state" id="intro-state">Pronto para editar</span></div><form id="intro-form" class="dialog-form"><input type="hidden" name="id"><label>Frase enviada depois que o perfil seguir<textarea name="response" rows="6" placeholder="Escreva o agradecimento e o primeiro convite."></textarea><small>Esta frase passa a valer para as próximas campanhas.</small></label><label>Quando usar<textarea name="context" rows="3"></textarea></label><div class="editor-actions">${button('Salvar frase','primary-button','save-intro')}<button class="ghost-button" type="button" id="reset-intro">↻ Restaurar texto carregado</button></div></form></section></div>`;
 let current=null;const form=el('#intro-form');
 const load=t=>{if(!t)return;current=t;form.elements.id.value=t.id;form.elements.response.value=t.response||'';form.elements.context.value=t.context||'';el('#intro-name').textContent=labels[t.id]||t.question||'Frase';document.querySelectorAll('[data-intro-id]').forEach(n=>n.classList.toggle('selected',n.dataset.introId===t.id));};
 document.querySelectorAll('[data-intro-id]').forEach(n=>n.onclick=()=>load(templates.find(t=>t.id===n.dataset.introId)));
 el('#reset-intro').onclick=()=>load(current);
 form.onsubmit=async event=>{event.preventDefault();if(!current)return;const saved=await call('saveResponseTemplate',{template:{...current,response:form.elements.response.value,context:form.elements.context.value}});Object.assign(current,saved);load(current);el('#intro-state').textContent='Frase salva no fluxo';setTimeout(()=>el('#intro-state').textContent='Pronto para editar',2500);report({message:'Frase de agradecimento salva e ativa na prospecção.'});};
 if(templates[0])load(templates[0]);
}

async function libraryView(){
 const templates=await call('responseLibrary');const content=activatePanel('Biblioteca de respostas','Edite a pergunta prevista, a resposta automática e os recursos de cada etapa do diálogo.');
 content.innerHTML=`<div class="library-layout"><aside class="flow-sidebar"><div class="flow-sidebar-head"><div><small>FLUXO COMERCIAL</small><h3>Respostas ativas</h3></div>${button('+ Nova resposta','primary-button','new-template')}</div><div class="stage-filter" id="stage-filter">${Object.entries(stageNames).map(([id,name])=>`<button data-stage="${id}">${name}</button>`).join('')}</div><div id="template-list" class="template-list">${templates.map((t,i)=>templateCard(t,i===0)).join('')||empty('▱','Sem respostas','Crie a primeira etapa do fluxo.')}</div></aside><section class="flow-editor"><div class="editor-title"><div><span class="eyebrow">EDITOR DE DIÁLOGO</span><h3 id="editor-name">Selecione uma resposta</h3></div><span class="save-state" id="save-state">Pronto para editar</span></div><form id="template-form" class="dialog-form"><input type="hidden" name="id"><label>Etapa do fluxo<select name="stage">${Object.entries(stageNames).map(([id,name])=>`<option value="${id}">${name}</option>`).join('')}</select></label><label>Pergunta ou situação prevista<textarea name="question" rows="3" placeholder="Ex.: A pessoa agradeceu o elogio"></textarea><small>O que o agente deve reconhecer antes de responder.</small></label><label>Resposta que o agente deve usar<textarea name="response" rows="5" placeholder="Escreva a resposta curta, natural e orientada ao próximo passo."></textarea><small>Esta resposta passa a ser memória do agente para diálogos semelhantes.</small></label><div class="form-columns"><label>Contexto e condições<textarea name="context" rows="4" placeholder="Quando usar, o que evitar e informações necessárias."></textarea></label><label>Links a considerar<textarea name="links" rows="4" placeholder="https://...\nLink de instalação ou página oficial"></textarea></label></div><label>Imagem ou material de apoio<textarea name="images" rows="2" placeholder="URL, nome do poster ou referência da biblioteca"></textarea></label><div class="editor-actions">${button('Salvar no fluxo','primary-button','save-template')}${button('Duplicar etapa','ghost-button','duplicate-template')}${button('Limpar','ghost-button','clear-template')}</div></form></section></div>`;
 let current=null,filter='';const form=el('#template-form');
 const load=item=>{current=item;form.id.value=item?.id||'';form.stage.value=item?.stage||'acolhimento';form.question.value=item?.question||'';form.response.value=item?.response||'';form.context.value=item?.context||'';form.links.value=item?.links||'';form.images.value=item?.images||'';el('#editor-name').textContent=item?`${stageNames[item.stage]||item.stage} · resposta automática`:'Nova resposta';document.querySelectorAll('[data-template-id]').forEach(n=>n.classList.toggle('selected',n.dataset.templateId===item?.id));};
 const renderList=()=>{el('#template-list').innerHTML=templates.filter(t=>!filter||t.stage===filter).map(t=>templateCard(t,current?.id===t.id)).join('')||empty('◌','Nenhuma resposta nesta etapa','Crie uma resposta para continuar o fluxo.');el('#template-list').querySelectorAll('[data-template-id]').forEach(n=>n.onclick=()=>load(templates.find(t=>t.id===n.dataset.templateId)));};
 el('#new-template').onclick=()=>load(null);el('#clear-template').onclick=()=>load(null);el('#duplicate-template').onclick=()=>{if(!current)return report({message:'Selecione uma resposta para duplicar.'});load({...current,id:'',question:`Cópia · ${current.question}`});};
 el('#stage-filter').querySelectorAll('button').forEach(b=>b.onclick=()=>{filter=filter===b.dataset.stage?'':b.dataset.stage;document.querySelectorAll('#stage-filter button').forEach(x=>x.classList.toggle('active',x===b&&filter));renderList();});
 form.onsubmit=async event=>{event.preventDefault();const template=Object.fromEntries(new FormData(form));const saved=await call('saveResponseTemplate',{template});const pos=templates.findIndex(t=>t.id===saved.id);if(pos<0)templates.unshift(saved);else templates[pos]=saved;load(saved);renderList();el('#save-state').textContent='Salvo na memória do agente';setTimeout(()=>el('#save-state').textContent='Pronto para editar',2500);report({message:'Etapa salva e disponível para as próximas respostas.'});};
 if(templates[0])load(templates[0]);
}

let flowChatLog=[];
let flowProposal=null;
let flowStateCache={revision:0,history:[],lessons:[],templates:[]};

function flowStageOptions(selected){return Object.entries(stageNames).map(([id,name])=>`<option value="${id}" ${id===selected?'selected':''}>${name}</option>`).join('');}
function flowOperationCard(op,index){
 const action=['add','update','remove'].includes(op.action)?op.action:'add';const preview=op.preview||{};const stage=op.stage||preview.stage||'descoberta';
 if(action==='remove')return `<article class="change-card remove" data-op-index="${index}"><div class="change-head"><span class="studio-badge remove">Remover</span><span class="flow-stage">${safe(stageNames[stage]||stage)}</span></div><div class="change-before"><strong>${safe(preview.question||op.question||'Resposta existente')}</strong><p>${safe(preview.response||'')}</p></div></article>`;
 const before=op.before||(action==='update'?preview:null);
 return `<article class="change-card ${action}" data-op-index="${index}"><div class="change-head"><span class="studio-badge ${action}">${action==='add'?'Nova':'Alterar'}</span><span class="flow-stage">${safe(stageNames[stage]||stage)}</span><small>${safe(op.id||'nova resposta')}</small></div><label class="change-field">Etapa do fluxo<select data-field="stage">${flowStageOptions(stage)}</select></label><label class="change-field">Pergunta ou situação prevista<textarea data-field="question" rows="2">${safe(op.question||'')}</textarea></label><label class="change-field">Resposta que o agente deve enviar<textarea data-field="response" rows="4">${safe(op.response||'')}</textarea></label><div class="change-grid"><label class="change-field">Quando usar e o que evitar<textarea data-field="context" rows="2">${safe(op.context||'')}</textarea></label><label class="change-field">Gatilhos da mensagem do lead<textarea data-field="match" rows="2" placeholder="já uso | já usamos | temos sistema">${safe(op.match||'')}</textarea></label></div>${before?`<div class="change-before"><small>Antes</small><strong>${safe(before.question||'')}</strong><p>${safe(before.response||'')}</p></div>`:''}</article>`;
}
function flowRenderProposal(){
 const card=el('#proposal-card');if(!card)return;
 if(!flowProposal){card.innerHTML=`<div class="section-heading"><h3>Alterações propostas</h3><span class="status-pill">em espera</span></div>${empty('✦','Nada para aplicar','Descreva o ajuste no campo ao lado. O agente devolve as mudanças para você revisar antes de gravar.')}`;return;}
 const ops=flowProposal.operations||[];const warnings=[...(flowProposal.warnings||[])].filter(Boolean);
 card.innerHTML=`<div class="section-heading"><h3>Alterações propostas</h3><span class="status-pill">${ops.length} mudança${ops.length===1?'':'s'}</span></div><p class="proposal-reply">${safe(flowProposal.reply||'')}</p><div class="proposal-summary"><strong>${safe(flowProposal.summary||'')}</strong><small>Base: versão ${safe(flowProposal.base_revision)} · ${flowProposal.source==='model'?'interpretado pelo modelo local':'interpretação local por regras'}</small></div>${warnings.length?`<ul class="proposal-warnings">${warnings.map(w=>`<li>${safe(w)}</li>`).join('')}</ul>`:''}<div class="change-list">${ops.map(flowOperationCard).join('')||empty('◌','Nenhuma operação','Reformule o pedido indicando a situação e a resposta desejada.')}</div>${ops.length?`<div class="editor-actions"><button class="primary-button" id="apply-proposal">✓ Aplicar na biblioteca</button><button class="ghost-button" id="discard-proposal">Descartar</button></div>`:''}`;
 card.querySelectorAll('[data-op-index]').forEach(node=>{const op=flowProposal.operations[Number(node.dataset.opIndex)];if(!op)return;node.querySelectorAll('[data-field]').forEach(field=>{field.oninput=()=>{op[field.dataset.field]=field.value;};});});
 const apply=el('#apply-proposal');if(apply)apply.onclick=()=>flowApplyProposal().catch(report);
 const discard=el('#discard-proposal');if(discard)discard.onclick=()=>{flowProposal=null;flowRenderProposal();};
}
async function flowRefreshState(){
 let state;
 try{state=await call('flowState');}catch(error){await new Promise(resolve=>setTimeout(resolve,450));state=await call('flowState');}
 flowStateCache=state;
 const version=el('#studio-version');if(version)version.textContent=`versão ${state.revision}`;
 flowRenderHistory(state.history||[]);flowRenderLessons(state.lessons||[]);
 if(flowProposal&&Number(flowProposal.base_revision)!==Number(state.revision)){flowProposal=null;flowRenderProposal();}
 waRenderSide();
}
function flowRenderHistory(rows){
 const card=el('#history-card');if(!card)return;
 const seed=Number(flowStateCache.revision)>0?`<article class="history-item"><div><strong>v0</strong><span>Roteiro semente</span></div><small>Biblioteca original</small><button class="ghost-button" data-revert="0">Reverter</button></article>`:'';
 card.innerHTML=`<div class="section-heading"><h3>Histórico de versões</h3><span class="status-pill">v${safe(flowStateCache.revision)}</span></div><div class="history-list">${rows.map(r=>`<article class="history-item"><div><strong>v${safe(r.revision)}</strong><span>${safe(r.summary||'Alteração')}</span></div><small>${formatTime(r.created_at)} · ${safe(r.source==='revert'?'reversão':r.source==='library'?'edição manual':'prompt')}</small><button class="ghost-button" data-revert="${safe(r.revision)}">Reverter</button></article>`).join('')||empty('◷','Sem versões','A primeira alteração aplicada aparece aqui.')}${seed}</div>`;
 card.querySelectorAll('[data-revert]').forEach(b=>b.onclick=()=>flowRevert(Number(b.dataset.revert)));
}
function flowRenderLessons(rows){
 const card=el('#lessons-card');if(!card)return;
 card.innerHTML=`<div class="section-heading"><h3>O que o agente aprendeu</h3><span class="status-pill">${rows.length}</span></div><div class="lesson-list">${rows.map(r=>`<article class="lesson-item"><strong>${safe(r.summary||'Ajuste de fluxo')}</strong><p>${safe(r.lesson||'')}</p><small>v${safe(r.revision)} · ${formatTime(r.created_at)}</small></article>`).join('')||empty('◌','Ainda sem aprendizados','Cada alteração aplicada entra na memória usada nas próximas respostas.')}</div>`;
}
let flowTestState={leadId:0,history:[],message:'',response:''};
async function flowTestLoad(leadId){
 const rows=await call('messages',{id:leadId});
 const history=rows.map(r=>({role:r[0],text:r[1]}));
 const lastUserIndex=history.map(r=>r.role).lastIndexOf('user');
 return {
  leadId,
  history:lastUserIndex>=0?history.slice(0,lastUserIndex):history,
  message:lastUserIndex>=0?history[lastUserIndex].text:'',
  response:''
 };
}
async function flowTestAsk(messageField,responseField,status){
 const message=String(messageField.value||'').trim();
 if(!message)return report({message:'Escreva a mensagem do cliente para testar.'});
 if(!flowTestState.leadId)return report({message:'Selecione uma conversa para testar.'});
 const history=flowTestState.history.slice();
 if(!history.length||history[history.length-1].text!==message)history.push({role:'user',text:message});
 status.textContent='Perguntando ao agente…';
 const answer=await call('draft',{id:flowTestState.leadId,browser_history:history});
 flowTestState.message=message;flowTestState.response=answer;
 responseField.value=answer;
 status.innerHTML=`<strong>Resposta atual do agente</strong><span>${safe(answer)}</span>`;
 return answer;
}
async function flowTestSave(messageField,responseField,status){
 if(!flowTestState.leadId)return report({message:'Selecione uma conversa para salvar o ajuste.'});
 const message=String(messageField.value||'').trim();
 const response=String(responseField.value||'').trim();
 if(!message||!response)return report({message:'Informe a mensagem do cliente e a resposta ajustada.'});
 const saved=await call('flowTeach',{message,response,lead_id:flowTestState.leadId});
 if(!saved.applied){report({message:saved.reason||'Nada foi alterado.'});return;}
 flowTestState.message=message;flowTestState.response=response;
 status.innerHTML=`<strong>Salvo na versão ${safe(saved.revision)}</strong><span>Perguntando de novo para confirmar…</span>`;
 const answer=await flowTestAsk(messageField,responseField,status);
 status.innerHTML=`<strong>Salvo na versão ${safe(saved.revision)} · teste da mesma pergunta</strong><span>${safe(answer)}</span>`;
 await flowRefreshState();
 report({message:`Resposta ajustada e salva na versão ${saved.revision}.`});
}
function flowRenderTest(leads){
 const card=el('#test-card');if(!card)return;
 if(!leads.length){card.innerHTML=`<div class="section-heading"><h3>Teste de diálogo</h3><span class="status-pill">sem conversas</span></div>${empty('◌','Nenhuma conversa para testar','Importe as DMs do Instagram ou crie um lead para repetir a pergunta do cliente.')}`;return;}
 const selected=leads.some(l=>Number(l.id)===Number(flowTestState.leadId))?Number(flowTestState.leadId):Number(leads[0].id);
 card.innerHTML=`<div class="section-heading"><h3>Teste de diálogo</h3><span class="status-pill">mesma pergunta</span></div><p class="test-hint">Escolha a conversa, repita a mensagem do cliente e veja se o agente devolve a resposta ajustada.</p><label class="test-field">Conversa<select id="test-lead">${leads.map(l=>`<option value="${safe(l.id)}" ${Number(l.id)===selected?'selected':''}>${safe(l.name)}${l.contact?' · '+safe(l.contact):''}</option>`).join('')}</select></label><label class="test-field">Mensagem do cliente<textarea id="test-message" rows="2" placeholder="Ex.: já uso outro sistema"></textarea></label><div class="test-actions"><button class="primary-button" id="test-ask">✦ Perguntar ao agente</button><button class="ghost-button" id="test-last">↺ Usar última mensagem</button></div><label class="test-field">Resposta do agente (edite e salve)<textarea id="test-response" rows="4" placeholder="A resposta do agente aparece aqui."></textarea></label><div class="test-actions"><button class="primary-button" id="test-save">✓ Salvar ajuste</button><button class="ghost-button" id="test-again">↻ Perguntar de novo</button></div><p class="test-status" id="test-status"></p>`;
 const leadSelect=el('#test-lead'),messageField=el('#test-message'),responseField=el('#test-response'),status=el('#test-status');
 const loadLead=async leadId=>{
  flowTestState=await flowTestLoad(leadId);
  messageField.value=flowTestState.message;responseField.value='';
  status.textContent=flowTestState.message?'Última mensagem do cliente carregada.':'Esta conversa ainda não tem mensagem do cliente.';
 };
 leadSelect.onchange=()=>loadLead(Number(leadSelect.value)).catch(report);
 el('#test-last').onclick=()=>loadLead(Number(leadSelect.value)).catch(report);
 el('#test-ask').onclick=()=>flowTestAsk(messageField,responseField,status).catch(report);
 el('#test-again').onclick=()=>flowTestAsk(messageField,responseField,status).catch(report);
 el('#test-save').onclick=()=>flowTestSave(messageField,responseField,status).catch(report);
 loadLead(selected).catch(report);
}
function flowAddMessage(role,text){
 flowChatLog.push({role,text});const thread=el('#operator-thread');if(!thread)return;
 thread.insertAdjacentHTML('beforeend',`<div class="operator-message ${role==='operator'?'operator':'agent'}">${role==='operator'?safe(text):`<p>${safe(text)}</p>`}</div>`);
 thread.scrollTop=thread.scrollHeight;
}
async function flowApplyProposal(){
 if(!flowProposal)return;const button=el('#apply-proposal');if(button){button.disabled=true;button.textContent='Aplicando…';}
 try{
  const result=await call('flowApply',{operations:flowProposal.operations,base_revision:flowProposal.base_revision,prompt:flowProposal.prompt||'',summary:flowProposal.summary||'',lesson:flowProposal.lesson||''});
  if(!result.applied){report({message:result.reason||'Nada foi alterado.'});return;}
  const learned=Number((result.learned||[]).length);
  flowProposal=null;flowRenderProposal();flowStateCache.revision=result.revision;const badge=el('#studio-version');if(badge)badge.textContent=`versão ${result.revision}`;flowAddMessage('agent',`Aplicado na versão ${result.revision}. ${result.summary}.${learned?` ${learned} aprendizado(s) gravado(s) na memória comercial.`:''}`);
  await flowRefreshState();
 }finally{const current=el('#apply-proposal');if(current){current.disabled=false;current.textContent='✓ Aplicar na biblioteca';}}
}
async function flowRevert(revision){
 if(!confirm(`Restaurar a versão ${revision} da biblioteca? A versão atual fica preservada no histórico.`))return;
 try{
  const result=await call('flowRevert',{revision});
  if(!result.applied){report({message:result.reason||'Nada foi alterado.'});return;}
  flowStateCache.revision=result.revision;const badge=el('#studio-version');if(badge)badge.textContent=`versão ${result.revision}`;
  flowAddMessage('agent',`Fluxos restaurados. Nova versão ${result.revision} criada a partir da versão ${result.restored_from}.`);
  await flowRefreshState();report({message:`Versão ${revision} restaurada.`});
 }catch(error){report(error);}
}

let waState={leadId:0,leads:[],thread:[],busy:false,epoch:0};
function waClock(value){
 const date=value?new Date(value):new Date();
 return Number.isNaN(date.getTime())?'':date.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
}
function waBubbleBody(text){
 const parts=String(text??'').split('[[AGENT_BUBBLE]]').map(part=>part.trim()).filter(Boolean);
 return parts.map(part=>`<p>${safe(part)}</p>`).join('')||'<p></p>';
}
function waBubbleHtml(message,index){
 if(message.role!=='agent'){
  return `<div class="wa-row client"><div class="wa-bubble client">${waBubbleBody(message.text)}<time>${safe(message.at||'')}</time></div></div>`;
 }
 return `<div class="wa-row agent" data-wa-row="${index}"><div class="wa-bubble agent">${waBubbleBody(message.text)}${message.saved?`<span class="wa-saved">✓ resposta oficial · v${safe(message.revision)}</span>`:''}<time>${safe(message.at||'')}</time></div><button class="wa-edit" data-wa-edit="${index}" title="Editar e salvar esta resposta no fluxo">✎ Editar resposta</button></div>`;
}
function waRenderSide(){
 const state=flowStateCache;
 const revision=el('#wa-revision');if(revision)revision.textContent=`v${state.revision||0}`;
 const tabVersion=el('#wa-version');if(tabVersion)tabVersion.textContent=`versão ${state.revision||0}`;
 const history=el('#wa-history');
 if(history){
  const rows=(state.history||[]).slice(0,8);
  history.innerHTML=rows.map(r=>`<article class="history-item"><div><strong>v${safe(r.revision)}</strong><span>${safe(r.summary||'Alteração')}</span></div><small>${formatTime(r.created_at)} · ${safe(r.source==='dialogue'?'ajuste no diálogo':r.source==='revert'?'reversão':r.source==='library'?'edição manual':'prompt')}</small><button class="ghost-button" data-wa-revert="${safe(r.revision)}">Reverter</button></article>`).join('')||empty('◷','Sem versões','Cada resposta ajustada no chat cria uma versão reversível.');
  history.querySelectorAll('[data-wa-revert]').forEach(b=>b.onclick=()=>flowRevert(Number(b.dataset.waRevert)).catch(report));
 }
 const lessons=el('#wa-lessons');
 if(lessons){
  const rows=(state.lessons||[]).slice(0,6);
  const count=el('#wa-lesson-count');if(count)count.textContent=String((state.lessons||[]).length);
  lessons.innerHTML=rows.map(r=>`<article class="lesson-item"><strong>${safe(r.summary||'Ajuste de fluxo')}</strong><p>${safe(r.lesson||'')}</p><small>v${safe(r.revision)} · ${formatTime(r.created_at)}</small></article>`).join('')||empty('◌','Ainda sem aprendizados','Cada resposta salva no balão vira conhecimento do agente.');
 }
}
function waRenderThread(){
 const thread=el('#wa-thread');if(!thread)return;
 thread.innerHTML=waState.thread.length
  ? waState.thread.map((message,index)=>waBubbleHtml(message,index)).join('')
  : empty('💬','Comece pelo cliente','Escreva a primeira mensagem como se fosse o lead. O agente responde com o fluxo oficial e você pode ajustar qualquer resposta.');
 thread.querySelectorAll('[data-wa-edit]').forEach(b=>b.onclick=()=>waOpenEditor(Number(b.dataset.waEdit)).catch(report));
 thread.scrollTop=thread.scrollHeight;
}
async function waLoadThread(leadId){
 waState.leadId=Number(leadId)||0;
 waState.epoch+=1;
 waState.busy=false;
 waState.thread=[];
 try{
  const rows=await call('messages',{id:waState.leadId});
  waState.thread=rows.map(r=>({role:r[0]==='assistant'?'agent':'user',text:r[1],at:waClock(r[2])}));
 }catch(error){waState.thread=[];}
 const lead=waState.leads.find(l=>Number(l.id)===Number(waState.leadId));
 if(lead){
  const name=el('#wa-name'),contact=el('#wa-contact'),avatar=el('#wa-avatar');
  if(name)name.textContent=lead.name;
  if(contact)contact.textContent=`${lead.contact||'Contato local'} · ambiente de teste, nada é enviado ao Instagram`;
  if(avatar)avatar.textContent=(lead.name||'?').slice(0,1);
 }
 waRenderThread();
}
async function waLoadLeads(preferred){
 const leads=await call('leads');
 waState.leads=leads;
 const select=el('#wa-lead');if(!select)return;
 if(!leads.length){
  select.innerHTML='<option value="">Sem conversas</option>';
  select.disabled=true;
  const send=el('#wa-send');if(send)send.disabled=true;
  const repeat=el('#wa-repeat');if(repeat)repeat.disabled=true;
  waState.thread=[];
  const thread=el('#wa-thread');
  if(thread)thread.innerHTML=`<div class="wa-empty"><strong>Nenhuma conversa para testar</strong><p>Crie uma conversa de teste para interpretar o cliente e ajustar as respostas do agente.</p><button class="primary-button" id="wa-create-lead">+ Criar conversa de teste</button></div>`;
  const create=el('#wa-create-lead');
  if(create)create.onclick=async()=>{
   create.disabled=true;create.textContent='Criando…';
   const id=await call('create',{name:'Teste de diálogo',contact:'teste.local'});
   await waLoadLeads(id);
   await refreshLeads().catch(()=>{});
  };
  return;
 }
 select.disabled=false;
 const send=el('#wa-send');if(send)send.disabled=false;
 const repeat=el('#wa-repeat');if(repeat)repeat.disabled=false;
 const current=preferred||waState.leadId||leads[0].id;
 const selected=leads.some(l=>Number(l.id)===Number(current))?Number(current):Number(leads[0].id);
 select.innerHTML=leads.map(l=>`<option value="${safe(l.id)}" ${Number(l.id)===selected?'selected':''}>${safe(l.name)}${l.contact?' · '+safe(l.contact):''}</option>`).join('');
 select.onchange=()=>waLoadThread(Number(select.value)).catch(report);
 if(!waState.thread.length||Number(waState.leadId)!==selected)await waLoadThread(selected);
 else waRenderThread();
}
async function waAskAgent(){
 if(waState.busy||!waState.leadId)return;
 const epoch=waState.epoch;
 waState.busy=true;
 const send=el('#wa-send');if(send)send.disabled=true;
 const thread=el('#wa-thread');
 const typing=document.createElement('div');
 typing.className='wa-row agent wa-typing';
 typing.innerHTML='<div class="wa-bubble agent"><span class="wa-dots"><i></i><i></i><i></i></span></div>';
 if(thread){thread.appendChild(typing);thread.scrollTop=thread.scrollHeight;}
 try{
  const history=waState.thread.map(message=>({role:message.role==='agent'?'assistant':'user',text:message.text}));
  const answer=await call('draft',{id:waState.leadId,browser_history:history});
  if(epoch!==waState.epoch)return;
  waState.thread.push({role:'agent',text:String(answer||'').trim(),at:waClock()});
 }finally{
  typing.remove();
  waState.busy=false;
  if(send)send.disabled=false;
  if(epoch===waState.epoch)waRenderThread();
 }
}
async function waRepeatText(text){
 const value=String(text||'').trim();
 if(!value)return report({message:'Escreva a mensagem do cliente antes de testar.'});
 if(!waState.leadId)return report({message:'Selecione ou crie uma conversa de teste.'});
 if(waState.busy)return;
 waState.thread.push({role:'user',text:value,at:waClock()});
 waRenderThread();
 await waAskAgent();
}
async function waOpenEditor(index){
 const thread=el('#wa-thread');if(!thread)return;
 const row=thread.querySelector(`[data-wa-row="${index}"]`);if(!row)return;
 const message=waState.thread[index];if(!message)return;
 const trigger=[...waState.thread.slice(0,index)].reverse().find(item=>item.role==='user');
 if(!trigger)return report({message:'Esta resposta não tem uma mensagem do cliente antes dela para vincular o ajuste.'});
 thread.querySelectorAll('.wa-editor').forEach(node=>node.remove());
 const editor=document.createElement('div');
 editor.className='wa-editor';
 editor.innerHTML=`<div class="wa-editor-head"><span>✎ Ajustar resposta do agente</span><button class="wa-editor-close" type="button" data-wa-close>✕</button></div><small>O cliente disse</small><blockquote>${safe(trigger.text)}</blockquote><label>Resposta que o agente deve enviar<textarea rows="4">${safe(message.text)}</textarea></label><div class="wa-editor-actions"><button class="primary-button" data-wa-save>✓ Salvar resposta</button><button class="ghost-button" data-wa-retest>↻ Testar a mesma pergunta</button></div><p class="wa-editor-result" hidden></p>`;
 row.insertAdjacentElement('afterend',editor);
 const field=editor.querySelector('textarea');
 const result=editor.querySelector('.wa-editor-result');
 const save=editor.querySelector('[data-wa-save]');
 editor.querySelector('[data-wa-close]').onclick=()=>editor.remove();
 editor.querySelector('[data-wa-retest]').onclick=()=>waRepeatText(trigger.text).catch(report);
 save.onclick=async()=>{
  const response=String(field.value||'').trim();
  if(!response){result.hidden=false;result.textContent='Escreva a resposta ajustada antes de salvar.';return;}
  save.disabled=true;save.textContent='Salvando…';
  try{
   const saved=await call('flowTeach',{message:trigger.text,response,lead_id:waState.leadId});
   if(!saved.applied){result.hidden=false;result.textContent=saved.reason||'A resposta já está salva para esta mensagem.';return;}
   message.text=response;message.saved=true;message.revision=saved.revision;
   const bubble=row.querySelector('.wa-bubble');
   if(bubble)bubble.innerHTML=`${waBubbleBody(response)}<span class="wa-saved">✓ resposta oficial · v${safe(saved.revision)}</span><time>${safe(message.at||'')}</time>`;
   const history=waState.thread.slice(0,index+1).map(item=>({role:item.role==='agent'?'assistant':'user',text:item.text}));
   let applied='';
   try{applied=String(await call('draft',{id:waState.leadId,browser_history:history})||'').trim();}catch(error){applied='';}
   result.hidden=false;
   if(applied&&applied!==response){
    result.innerHTML=`<strong>Salvo na versão ${safe(saved.revision)} · regra oficial prevalece</strong><span>Esta mensagem também aciona uma regra fixa de segurança, cobrança ou atendimento humano, que continua acima do fluxo. O agente responde: ${safe(applied)}</span>`;
   }else{
    result.innerHTML=`<strong>Salvo na versão ${safe(saved.revision)} · aprendizado gravado</strong><span>Ao repetir “${safe(trigger.text)}”, o agente responde com a versão ajustada. Continue o diálogo normalmente.</span>`;
   }
   await flowRefreshState();
   report({message:`Resposta ajustada e salva na versão ${saved.revision}.`});
  }catch(error){report(error);}
  finally{save.disabled=false;save.textContent='✓ Salvar resposta';}
 };
 field.focus();
}
async function operatorView(){
 const content=activatePanel('Diálogo com o agente','Converse como o cliente. Edite qualquer resposta do agente direto no balão e ela vira a resposta oficial do fluxo.');
 content.innerHTML=`<div class="operator-tabs" role="tablist"><button class="active" data-operator-tab="chat">💬 Testar diálogo</button><button data-operator-tab="prompt">✦ Ajustar por prompt</button><span class="operator-tabs-note" id="wa-version">versão …</span></div><section class="wa-panel" id="wa-panel"><div class="wa-layout"><aside class="wa-side"><label class="wa-field">Conversa de teste<select id="wa-lead"></select></label><p class="wa-hint">Você interpreta o cliente. O agente responde com o fluxo oficial; ao editar uma resposta, ela vira a resposta validada para aquela mensagem.</p><section class="data-card"><div class="section-heading"><h3>Histórico de versões</h3><span class="status-pill" id="wa-revision">v0</span></div><div class="history-list" id="wa-history"></div></section><section class="data-card"><div class="section-heading"><h3>O que o agente aprendeu</h3><span class="status-pill" id="wa-lesson-count">0</span></div><div class="lesson-list" id="wa-lessons"></div></section></aside><div class="wa-chat"><header class="wa-head"><span class="wa-avatar" id="wa-avatar">?</span><div><strong id="wa-name">Conversa de teste</strong><small id="wa-contact">Ambiente de teste · nada é enviado ao Instagram</small></div><span class="wa-live">● testando</span></header><div class="wa-thread" id="wa-thread"></div><form class="wa-composer" id="wa-form"><textarea id="wa-input" rows="1" placeholder="Escreva como o cliente… (Enter envia, Shift+Enter quebra linha)"></textarea><button type="button" class="ghost-button" id="wa-repeat" title="Reenviar a última mensagem do cliente">↻ Repetir</button><button type="submit" class="primary-button" id="wa-send">➤ Enviar</button></form></div></div></section><section id="operator-panel" hidden></section>`;
 const tabs=[...content.querySelectorAll('[data-operator-tab]')];
 const showTab=async name=>{
  tabs.forEach(tab=>tab.classList.toggle('active',tab.dataset.operatorTab===name));
  const chat=el('#wa-panel'),prompt=el('#operator-panel');
  if(chat)chat.hidden=name!=='chat';
  if(prompt)prompt.hidden=name!=='prompt';
  if(name==='prompt'&&prompt&&!prompt.dataset.ready){prompt.dataset.ready='1';await flowPromptPanel();}
 };
 tabs.forEach(tab=>tab.onclick=()=>showTab(tab.dataset.operatorTab).catch(report));
 const form=el('#wa-form'),input=el('#wa-input');
 input.onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();form.requestSubmit();}};
 form.onsubmit=event=>{
  event.preventDefault();
  const value=String(input.value||'').trim();
  if(!value)return;
  input.value='';input.style.height='auto';
  waRepeatText(value).catch(report);
 };
 el('#wa-repeat').onclick=()=>{
  const last=[...waState.thread].reverse().find(message=>message.role==='user');
  if(!last)return report({message:'Ainda não há mensagem do cliente para repetir.'});
  waRepeatText(last.text).catch(report);
 };
 await flowRefreshState();
 await waLoadLeads();
 waRenderSide();
}

async function flowPromptPanel(){
 const content=el('#operator-panel');if(!content)return;
 content.innerHTML=`<div class="flow-studio"><section class="operator-chat"><div class="studio-head"><div><p class="eyebrow">AJUSTE POR PROMPT</p><h3>Ajuste o diálogo conversando</h3><p>O agente lê a biblioteca ativa, interpreta sua instrução e propõe respostas por etapa. Cada aplicação gera uma versão reversível e um aprendizado na memória comercial.</p></div><span class="status-pill" id="studio-version">versão …</span></div><div id="operator-thread" class="operator-thread"></div><div class="example-chips"><button data-example="Quando a clínica disser que já usa outro sistema, pergunte qual é antes de falar do comparativo.">Objeção de concorrente</button><button data-example="Quando o lead perguntar sobre preço, responda que o valor depende do tamanho da equipe e pergunte quantos profissionais atendem hoje.">Objeção de preço</button><button data-example="Na etapa proposta, troque a resposta do link para explicar que os 3 meses começam após a ativação acompanhada.">Link de 3 meses</button><button data-example="Na etapa follow-up, crie uma retomada para quem não respondeu depois de 3 dias.">Follow-up</button></div><form id="operator-form" class="operator-composer"><div class="composer-top"><select name="stage">${flowStageOptions('descoberta')}</select><small>Ctrl+Enter envia</small></div><textarea name="message" required rows="4" placeholder="Ex.: quando a clínica disser que usa outro sistema, pergunte qual é antes de enviar o comparativo."></textarea><details><summary>Adicionar contexto, links ou imagens</summary><textarea name="context" rows="2" placeholder="Informações que o agente precisa considerar"></textarea><textarea name="links" rows="2" placeholder="Links oficiais"></textarea><textarea name="images" rows="2" placeholder="Imagem/poster de apoio"></textarea></details><div class="composer-row"><small>A alteração só entra na biblioteca depois de você revisar e aplicar.</small><button class="primary-button" type="submit">✦ Interpretar ajuste</button></div></form></section><aside class="studio-side"><section class="data-card" id="proposal-card"></section><section class="data-card" id="history-card"></section><section class="data-card" id="lessons-card"></section></aside></div>`;
 const thread=el('#operator-thread');
 if(!flowChatLog.length)flowChatLog.push({role:'agent',text:'Olá, Denis. Descreva em português o que deve mudar no diálogo. Eu interpreto, mostro o diff e só gravo depois da sua confirmação.'});
 thread.innerHTML=flowChatLog.map(m=>`<div class="operator-message ${m.role==='operator'?'operator':'agent'}">${m.role==='operator'?safe(m.text):`<p>${safe(m.text)}</p>`}</div>`).join('');
 thread.scrollTop=thread.scrollHeight;
 const form=el('#operator-form');const messageField=form.querySelector('textarea[name="message"]');
 form.querySelectorAll('[data-example]').forEach(b=>b.onclick=()=>{messageField.value=b.dataset.example;messageField.focus();});
 messageField.onkeydown=event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();form.requestSubmit();}};
 form.onsubmit=async event=>{
  event.preventDefault();const data=Object.fromEntries(new FormData(form));const message=String(data.message||'').trim();if(!message)return;
  const prior=flowChatLog.slice(-6).map(m=>({role:m.role,text:m.text}));
  flowAddMessage('operator',message);const button=form.querySelector('button[type="submit"]');button.disabled=true;button.textContent='Interpretando…';
  try{
   const proposal=await call('flowChat',{message,stage:data.stage,context:data.context,links:data.links,images:data.images,history:prior});
   flowProposal={...proposal,prompt:message};flowAddMessage('agent',proposal.reply);flowRenderProposal();form.reset();form.stage.value=data.stage||'descoberta';
  }catch(error){flowAddMessage('agent',`Não consegui interpretar o ajuste: ${error.message||error}`);report(error);}
  finally{button.disabled=false;button.textContent='✦ Interpretar ajuste';thread.scrollTop=thread.scrollHeight;}
 };
 flowRenderProposal();flowRenderHistory(flowStateCache.history||[]);flowRenderLessons(flowStateCache.lessons||[]);
 await flowRefreshState();
}

async function crmView(){const leads=await call('leads');const content=activatePanel('Leads e CRM','Visão comercial das conversas persistidas localmente.');content.innerHTML=`<div class="crm-overview"><article><small>LEADS CADASTRADOS</small><strong>${leads.length}</strong></article><article><small>MAIOR INTENÇÃO</small><strong>${Math.max(0,...leads.map(l=>Number(l.score)||0))}</strong></article><article><small>PRÓXIMAS AÇÕES</small><strong>${leads.filter(l=>l.next_action).length}</strong></article></div><section class="data-card"><div class="section-heading"><h3>Lista de oportunidades</h3>${button('+ Novo lead','primary-button','crm-new')}</div><div class="responsive-table"><table><thead><tr><th>Lead</th><th>Contato</th><th>Etapa</th><th>Score</th><th>Próxima ação</th></tr></thead><tbody>${leads.map(l=>`<tr><td><strong>${safe(l.name)}</strong></td><td>${safe(l.contact||'—')}</td><td><span class="status-pill">${safe(l.stage||'Novo')}</span></td><td>${safe(l.score)}</td><td>${safe(l.next_action||'—')}</td></tr>`).join('')||'<tr><td colspan="5">Nenhum lead cadastrado.</td></tr>'}</tbody></table></div></section>`;el('#crm-new').onclick=()=>el('#new-lead')?.click();}
async function recordsView(type){const rows=await call('records',{type});const isCampaign=type==='campaigns';const title=isCampaign?'Campanhas':'Follow-ups';const content=activatePanel(title,isCampaign?'Acompanhe as respostas preparadas, pendentes e concluídas.':'Organize retomadas sem perder o contexto comercial.');content.innerHTML=`<div class="record-grid">${rows.map(r=>`<article class="record-card"><div><span class="record-icon">${isCampaign?'↗':'◷'}</span><span class="status-pill">${safe(r.status||'agendado')}</span></div><h3>${safe(r.action||r.kind||'Ação comercial')}</h3><p>${safe(r.rationale||r.note||r.payload||'Sem detalhes adicionais.')}</p><small>${formatTime(r.created_at||r.due_at)}</small>${isCampaign&&r.status==='pending'?button('Aprovar envio','primary-button',`approve-${r.id}`):''}</article>`).join('')||empty(isCampaign?'↗':'◷',`Nenhuma ${isCampaign?'campanha':'retomada'} pendente`,isCampaign?'As mensagens preparadas aparecerão aqui.':'Gere um follow-up a partir de uma conversa.')}</div>`;if(isCampaign)rows.filter(r=>r.status==='pending').forEach(r=>{const b=el(`#approve-${r.id}`);if(b)b.onclick=async()=>{await call('approveReply',{id:r.id});await recordsView(type);report({message:'Resposta aprovada.'});};});}
async function campaignsView(){const content=activatePanel('Campanhas','A prospecção percorre o feed, encontra perfis do público adequado e cria uma fila contextual para a abordagem.');const rows=await call('records',{type:'campaigns'});content.innerHTML=`<div class="module-heading"><div><p class="eyebrow">PROSPECÇÃO GUIADA</p><h3>Encontrar oportunidades no feed</h3><p>O agente percorre o feed, analisa perfis públicos e prepara a sequência contextual de interação.</p></div>${button('◌ Iniciar prospecção','primary-button','scan-feed')}</div><div class="record-grid" id="campaign-grid">${rows.map(r=>{let p={};try{p=JSON.parse(r.payload||'{}')}catch{}return `<article class="record-card"><div><span class="record-icon">◌</span><span class="status-pill">${safe(r.status)}</span></div><h3>@${safe(p.username||'perfil')}</h3><p>${safe(r.rationale||'Perfil avaliado pelo agente.')}</p><small>${safe(p.intro||'Olá! Muito legal o trabalho de vocês ❤️')}</small></article>`}).join('')||empty('◌','Nenhuma oportunidade na fila','Abra o feed no navegador interno e clique em Iniciar prospecção.')}</div>`;el('#scan-feed').onclick=async()=>{const b=el('#scan-feed');b.disabled=true;b.textContent='Analisando perfis…';try{const result=await window.sales.scanFeedProfiles();report({message:`${result.scanned} perfis analisados; ${result.created.length} oportunidades adicionadas à campanha.`});await campaignsView();}finally{if(el('#scan-feed'))el('#scan-feed').disabled=false;}};}
async function followupsView(){const rows=await call('followupRecords');const content=activatePanel('Follow-ups','Retomadas organizadas por data, com rascunho e contexto do lead.');content.innerHTML=`<div class="record-grid">${rows.map(r=>`<article class="record-card"><div><span class="record-icon">◷</span><span class="status-pill">${safe(r.status)}</span></div><h3>${safe(r.name)} · ${formatTime(r.due_at)}</h3><p>${safe(r.draft||r.task)}</p><small>${safe(r.contact||'Sem contato')}</small>${r.done?'<small>Concluído</small>':button('Concluir follow-up','primary-button',`done-followup-${r.id}`)}</article>`).join('')||empty('◷','Nenhum follow-up pendente','Selecione uma conversa e gere um follow-up para organizar a retomada.')}</div>`;rows.filter(r=>!r.done).forEach(r=>{const b=el(`#done-followup-${r.id}`);if(b)b.onclick=async()=>{await call('completeFollowup',{id:r.id});await followupsView();report({message:'Follow-up concluído.'});};});}
async function connectionView(statusOnly=false){const [data,agent]=await Promise.all([call('status'),call('agentStatus')]);const content=activatePanel(statusOnly?'Status dos serviços':'Integração Instagram/Meta',statusOnly?'Verificação local das dependências do agente.':'Conexão, sincronização e autorização usadas pelo CRM.');const cycle=agent.worker_cycle||{};const heartbeat=agent.worker_heartbeat_at?formatTime(agent.worker_heartbeat_at):'Aguardando primeiro ciclo';const browser=cycle.browser||{};const browserState={paused:'Pausado',offline:'Indisponível','waiting-login':'Aguardando acesso',thread:'Lendo conversa',message:'Atendendo mensagem',sweep:'Verificando conversas',ready:'Pronto',unknown:'Aguardando'}[browser.state||'unknown'];const automation={status:agent.active&&agent.worker_heartbeat_at?'connected':agent.active?'attention':'not_configured',label:'Automação comercial',detail:agent.active?`Worker ativo · último ciclo ${heartbeat} · sessão interna: ${browserState} · fila ${Number(cycle.queued||0)}.`:'Agente automático desativado no painel.',meta:{}};const entries=[...Object.entries(data),['automation',automation]];content.innerHTML=`<div class="health-grid">${entries.map(([key,v])=>`<article class="health-card"><span class="health-dot ${safe(v.status||'unknown')}"></span><div><small>${safe(v.label||key)}</small><strong>${safe(v.status||'Indefinido')}</strong><p>${safe(v.detail||'Sem detalhes')}</p></div></article>`).join('')}</div><div class="integration-actions">${!statusOnly?button('Reconectar Instagram/Meta','primary-button','meta-reconnect'):''}${button('Atualizar status','ghost-button','refresh-health')}</div>`;const refresh=()=>connectionView(statusOnly).catch(report);el('#refresh-health').onclick=refresh;const reconnect=el('#meta-reconnect');if(reconnect)reconnect.onclick=async()=>{const auth=await call('metaOAuthUrl');await window.sales.openExternal(auth.url);report({message:'Autorização Meta aberta no navegador externo.'});};}
async function trialLinksView(){const offer=await call('trialOffer');const policy=offer.billing_policy||{};const content=activatePanel('Oferta de 3 meses','Os dois links abaixo são encaminhados automaticamente conforme o lead atende em clínica/equipe ou individualmente.');content.innerHTML=`<div class="knowledge-layout"><form id="trial-links-form" class="dialog-form"><h3>Configuração oficial</h3><label>Empresa responsável<input name="company_name" required></label><label>Site oficial<input name="company_url" type="url" required></label><label>Link · Clínica/equipe (Multi)<input name="clinic_url" type="url" required></label><label>Nome do produto para clínica<input name="clinic_name" required></label><label>Link · Profissional individual (Pro)<input name="professional_url" type="url" required></label><label>Nome do produto individual<input name="professional_name" required></label><label>Orientação de ativação<textarea name="activation" rows="4" required></textarea></label>${button('Salvar links de três meses','primary-button')}</form><section class="data-card"><div class="section-heading"><h3>Como o agente encaminha</h3><span class="status-pill">3 meses grátis</span></div><div class="knowledge-item"><strong>Clínica ou equipe</strong><p id="clinic-preview"></p></div><div class="knowledge-item"><strong>Profissional individual</strong><p id="professional-preview"></p></div><div class="operator-note">O agente só mostra o link depois de entender se a pessoa atende em clínica/equipe ou individualmente. O período começa após a ativação acompanhada.</div><div class="policy-callout"><strong>Sem cobrança automática</strong><p id="trial-policy-summary"></p><p>O aviso é enviado 10 dias antes do fim. Ao encerrar, o acesso fica indisponível, os dados são exportados em formato bruto criptografado e há 15 dias para confirmar a continuidade antes da exclusão segura na nuvem.</p></div></section></div>`;const f=el('#trial-links-form');const fill=value=>{f.company_name.value=value.company_name;f.company_url.value=value.company_url;f.clinic_url.value=value.clinic.url;f.clinic_name.value=value.clinic.name;f.professional_url.value=value.professional.url;f.professional_name.value=value.professional.name;f.activation.value=value.activation;el('#clinic-preview').textContent=`${value.clinic.name}: ${value.clinic.url}`;el('#professional-preview').textContent=`${value.professional.name}: ${value.professional.url}`;el('#trial-policy-summary').textContent=(value.billing_policy||policy).summary||'Não há conversão automática para plano pago.';};fill(offer);f.onsubmit=async event=>{event.preventDefault();const v=Object.fromEntries(new FormData(f));const saved=await call('saveTrialOffer',{offer:{company_name:v.company_name,company_url:v.company_url,activation:v.activation,clinic:{name:v.clinic_name,url:v.clinic_url},professional:{name:v.professional_name,url:v.professional_url}}});fill(saved);report({message:'Links e política de teste salvos: nenhuma cobrança automática será feita.'});};}
async function researchView(){const content=activatePanel('Pesquisa e aprendizado','Documente métodos, materiais e evidências que devem enriquecer as respostas do agente.');content.innerHTML=`<div class="knowledge-layout"><form id="knowledge-form" class="dialog-form"><h3>Novo material para a memória</h3><label>Título<input name="title" required placeholder="Ex.: Comparativo de agenda clínica"></label><label>Fonte ou URL<input name="source" placeholder="https://..."></label><label>Categoria<select name="category"><option value="playbook">Método de vendas</option><option value="product">Produto</option><option value="comparison">Comparativo</option></select></label><label>Conteúdo e aplicação<textarea name="content" required rows="8" placeholder="Registre fatos, exemplos, regras e como o agente deve aplicar este conteúdo."></textarea></label>${button('Guardar na memória','primary-button')}</form><section class="data-card"><div class="section-heading"><h3>Materiais já guardados</h3><span class="status-pill" id="knowledge-count">0</span></div><div id="knowledge-list"></div></section></div>`;const render=async()=>{const rows=await call('knowledge');el('#knowledge-count').textContent=rows.length;el('#knowledge-list').innerHTML=rows.map(r=>`<article class="knowledge-item"><strong>${safe(r[1])}</strong><p>${safe(r[3]).slice(0,280)}${String(r[3]).length>280?'…':''}</p><small>${safe(r[2]||'Sem tags')} · ${formatTime(r[5])}</small></article>`).join('')||empty('▱','Memória vazia','Adicione o primeiro conteúdo acima.');};el('#knowledge-form').onsubmit=async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.target));await call('saveDocument',{source:data.source||'manual:'+data.title,title:data.title,content:data.content,category:data.category});event.target.reset();await render();report({message:'Material salvo na memória comercial.'});};await render();}
async function moduleView(type){if(type==='follow-intro')return followIntroView();if(type==='library')return libraryView();if(type==='operator')return operatorView();if(type==='trial-links')return trialLinksView();if(type==='crm')return crmView();if(type==='campaigns')return campaignsView();if(type==='followups')return followupsView();if(type==='integration')return connectionView(false);if(type==='status')return connectionView(true);if(type==='research')return researchView();}
async function boot(){const agentButton=el('#agent-toggle');const prospectingButton=el('#prospecting-toggle');const refreshAgent=async()=>{const state=await call('agentStatus');agentButton.textContent=state.active?'■ Desativar agente automático':'▶ Ativar agente de vendas';agentButton.className=state.active?'primary-button':'ghost-button';agentButton.setAttribute('aria-pressed',String(state.active));if(prospectingButton){prospectingButton.textContent=state.prospecting_active?'◌ Pausar prospecção ativa':'◌ Ativar prospecção ativa';prospectingButton.className=state.prospecting_active?'primary-button':'ghost-button';prospectingButton.setAttribute('aria-pressed',String(state.prospecting_active));prospectingButton.disabled=!state.active;}};agentButton.onclick=async()=>{const state=await call('agentStatus');const next=await call('setAgentActive',{active:!state.active});if(!next.active)await call('setProspectingActive',{active:false});await refreshAgent();report({message:next.active?'Agente de vendas ativado.':'Agente de vendas desativado.'});};if(prospectingButton)prospectingButton.onclick=async()=>{const state=await call('agentStatus');const next=await call('setProspectingActive',{active:!state.prospecting_active});await refreshAgent();report({message:next.active?'Prospecção ativa liberada.':'Prospecção ativa pausada.'});};bindBrowserControls();await Promise.all([refreshAgent(),refreshSystemSummary()]);await refreshLeads();el('#generate-btn').onclick=async()=>{if(!selectedLead)return report({message:'Selecione uma conversa primeiro.'});el('#draft-text').textContent='Gerando resposta…';el('#draft-text').textContent=await call('draft',{id:selectedLead.id});};el('#queue-btn').onclick=async()=>{if(!selectedLead)return report({message:'Selecione uma conversa primeiro.'});const r=await call('queue',{id:selectedLead.id,text:el('#draft-text').textContent});report({message:`Resposta ${r.id} preparada na fila.`});};el('#pause-btn').onclick=async()=>{if(!selectedLead)return report({message:'Selecione uma conversa primeiro.'});await call('pause',{id:selectedLead.id});report({message:'Conversa pausada.'});};el('#followup-btn').onclick=async()=>{if(!selectedLead)return report({message:'Selecione uma conversa primeiro.'});await call('followup',{id:selectedLead.id,text:el('#draft-text').textContent});report({message:'Follow-up salvo.'});};document.querySelectorAll('.nav-item[data-view]').forEach(b=>b.addEventListener('click',()=>{const type=b.dataset.view;if(type!=='conversations')moduleView(type).catch(report);}));try{const remote=await window.sales.remoteMode?.();if(remote){const state=await call('internalBrowserStatus');if(state?.running)await vpsInternalBrowserView();}}catch(error){}}
boot().catch(report);
