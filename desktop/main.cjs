const {app, BrowserWindow, dialog, ipcMain, shell, clipboard} = require('electron');
const http = require('node:http');
const {spawn} = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const crypto = require('node:crypto');
// A edição remota pode coexistir com a edição local sem disputar o lock do
// Electron nem a pasta de dados do usuário.
if(path.basename(process.execPath).toLowerCase().includes('controle')) app.setName('AgenteVendasControleVPS');
let window;
let browserView;
let followerWindow;
let browserPaneUrl='https://www.instagram.com/';
let browserAttached=false;
let browserUserVisible=false;
let metaCallbackServer;
let backendChild=null;
let backendBuffer='';
let backendSequence=0;
const backendPending=new Map();
let localLlmChild=null;
let remoteTunnelChild=null;
const localLlmPort=11535;
function remoteControlConfig(){
  const candidates=[path.join(process.resourcesPath,'remote-control.json'),path.join(app.getPath('userData'),'remote-control.json')];
  for(const file of candidates){try{const config=JSON.parse(fs.readFileSync(file,'utf8'));if(config?.enabled&&config?.sshHost)return config;}catch{}}
  return null;
}
const remoteControl=remoteControlConfig();
function startRemoteTunnel(){
  if(!remoteControl||(remoteTunnelChild&&!remoteTunnelChild.killed))return;
  const executable=process.env.WINDIR?path.join(process.env.WINDIR,'System32','OpenSSH','ssh.exe'):'ssh';
  const port=String(remoteControl.localPort||8787);
  remoteTunnelChild=spawn(executable,['-N','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-L',`${port}:127.0.0.1:${remoteControl.remotePort||8787}`,remoteControl.sshHost],{windowsHide:true,stdio:'ignore'});
  remoteTunnelChild.on('close',()=>{remoteTunnelChild=null;});
}
function remoteBackend(command,args={}){return new Promise((resolve,reject)=>{
  startRemoteTunnel();
  const body=Buffer.from(JSON.stringify({id:++backendSequence,command,args}));
  const request=http.request({hostname:'127.0.0.1',port:remoteControl.localPort||8787,path:'/api/rpc',method:'POST',headers:{'Content-Type':'application/json','Content-Length':body.length},timeout:120000},response=>{let raw='';response.on('data',part=>raw+=part);response.on('end',()=>{try{const payload=JSON.parse(raw);payload.ok?resolve(payload.result):reject(new Error(payload.error||'Falha do agente na VPS.'));}catch{reject(new Error('Resposta inválida do agente na VPS.'));}});});
  request.on('timeout',()=>request.destroy(new Error('A VPS demorou para responder.')));
  request.on('error',error=>reject(new Error(`Controle remoto indisponível: ${error.message}`)));
  request.write(body);request.end();
});}
function localLlmPaths(){
  const root=app.isPackaged?path.join(process.resourcesPath,'native'):path.join(__dirname,'..','native');
  return {server:path.join(root,'runtime','llama-server.exe'),model:path.join(root,'models','qwen3-sales.gguf')};
}
function startEmbeddedLlm(){
  if(localLlmChild&&!localLlmChild.killed)return true;
  const {server,model}=localLlmPaths();
  if(!fs.existsSync(server)||!fs.existsSync(model))return false;
  localLlmChild=spawn(server,['-m',model,'--host','127.0.0.1','--port',String(localLlmPort),'-c','2048','-ngl','0'],{windowsHide:true,stdio:'ignore'});
  localLlmChild.on('close',()=>{localLlmChild=null;});
  return true;
}
function chromeExecutable(){
  const candidates=[
    path.join(process.env.PROGRAMFILES||'','Google','Chrome','Application','chrome.exe'),
    path.join(process.env['PROGRAMFILES(X86)']||'','Google','Chrome','Application','chrome.exe'),
    path.join(process.env.LOCALAPPDATA||'','Google','Chrome','Application','chrome.exe')
  ];
  return candidates.find(item=>item&&fs.existsSync(item))||'';
}
function openInChrome(url){
  const executable=chromeExecutable();
  if(!executable) throw new Error('Google Chrome não foi encontrado neste computador.');
  spawn(executable,[String(url)],{detached:true,stdio:'ignore',windowsHide:true}).unref();
}
function metaVaultEnv(){
  const root=path.join(process.env.LOCALAPPDATA||'', 'SalesAgentLocal', 'meta-vault');
  for(const dir of [root,path.join(__dirname,'..','.meta-vault')]){try{
    const envelope=JSON.parse(fs.readFileSync(path.join(dir,'secure-config.enc.json')));
    const key=crypto.createHash('sha256').update(fs.readFileSync(path.join(dir,'.master-key'))).digest();
    const decipher=crypto.createDecipheriv('aes-256-gcm',key,Buffer.from(envelope.iv,'base64'));
    decipher.setAuthTag(Buffer.from(envelope.tag,'base64'));
    const cfg=JSON.parse(Buffer.concat([decipher.update(Buffer.from(envelope.data,'base64')),decipher.final()]).toString());
    return {...process.env,...cfg};
  }catch{} }
  return {...process.env};
}
const backendAllowed=['leads','create','messages','message','draft','queue','pause','followup','knowledge','saveKnowledge','responseLibrary','saveResponseTemplate','operatorAssist','trialOffer','saveTrialOffer','browserImportThread','campaignDiscover','followupRecords','completeFollowup','status','records','syncHistory','syncPostflow','analytics','saveDocument','ragContext','comparison','competitorCatalog','competitorMatch','competitorSeed','research','personality','probabilities','trial','outcome','installation','approveReply','dispatchDue','agentCycle','agentStatus','setAgentActive','followerCycle','followerConfirm','followerReset','startServices','browserScreenCycle','browserScreenConfirm','browserScreenReset','replyDelay','postflowStatus','metaStatus','metaOAuthUrl','metaOAuthExchange','browserHealth','browserTools','browserSnapshot','browserAct','browserInstagramInbox','browserRead'];
function ensureBackend(){
  if(backendChild&&!backendChild.killed)return backendChild;
  const root=path.join(__dirname,'..');
  const packaged=path.join(process.resourcesPath,'SalesAgentBackend.exe');
  const embedded=startEmbeddedLlm();
  const env={...metaVaultEnv(),SALES_AGENT_RPC_STREAM:'1',...(embedded?{LOCAL_LLM_URL:`http://127.0.0.1:${localLlmPort}`,LOCAL_LLM_MODEL:'qwen3-sales'}:{})};
  backendChild=app.isPackaged?spawn(packaged,[],{windowsHide:true,env}):spawn('python',['-m','core.desktop_rpc'],{cwd:root,windowsHide:true,env});
  backendBuffer='';
  backendChild.stdout.on('data',data=>{
    backendBuffer+=data.toString();let newline;
    while((newline=backendBuffer.indexOf('\n'))>=0){
      const line=backendBuffer.slice(0,newline).trim();backendBuffer=backendBuffer.slice(newline+1);
      if(!line)continue;
      try{const response=JSON.parse(line);const pending=backendPending.get(response.id);if(!pending)continue;backendPending.delete(response.id);clearTimeout(pending.timer);response.ok?pending.resolve(response.result):pending.reject(new Error(response.error));}catch{}
    }
  });
  const fail=error=>{for(const pending of backendPending.values()){clearTimeout(pending.timer);pending.reject(error);}backendPending.clear();backendChild=null;};
  backendChild.on('error',fail);
  backendChild.on('close',()=>fail(new Error('O serviço interno do agente foi reiniciado. Tente novamente.')));
  return backendChild;
}
function backend(command,args={}) {
  if(remoteControl){
    if(!backendAllowed.includes(command))return Promise.reject(new Error('Comando inválido'));
    return remoteBackend(command,args);
  }
  return new Promise((resolve,reject)=>{
  if(!backendAllowed.includes(command))return reject(new Error('Comando inválido'));
  const child=ensureBackend();const id=++backendSequence;
  const timer=setTimeout(()=>{backendPending.delete(id);reject(new Error('O serviço interno demorou para responder.'));},120000);
  backendPending.set(id,{resolve,reject,timer});
  child.stdin.write(JSON.stringify({id,command,args})+'\n',error=>{if(error){clearTimeout(timer);backendPending.delete(id);reject(error);}});
});}
function startMetaCallbackServer(){
  if(metaCallbackServer) return;
  metaCallbackServer=http.createServer(async(req,res)=>{
    try{
      const url=new URL(req.url||'/', 'http://127.0.0.1:8765');
      if(url.pathname!=='/meta/callback'){res.writeHead(404);res.end('Not found');return;}
      const code=url.searchParams.get('code')||'';
      const state=url.searchParams.get('state')||'';
      const error=url.searchParams.get('error_description')||url.searchParams.get('error')||'';
      if(error) throw new Error(error);
      if(!code) throw new Error('A Meta não retornou o código OAuth.');
      const result=await backend('metaOAuthExchange',{code,state});
      res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});
      res.end('<!doctype html><meta charset="utf-8"><title>Meta conectada</title><body style="font-family:system-ui;padding:40px;background:#07111f;color:white"><h1>Instagram/Meta conectado</h1><p>Você pode voltar ao Agente de Vendas Local.</p><script>setTimeout(()=>window.close(),1200)</script></body>');
      if(window&&!window.isDestroyed()) window.webContents.send('sales:metaConnected',result);
    }catch(error){
      res.writeHead(400,{'Content-Type':'text/html; charset=utf-8'});
      res.end('<!doctype html><meta charset="utf-8"><title>Falha na conexão</title><body style="font-family:system-ui;padding:40px"><h1>Falha ao conectar Meta</h1><p>'+String(error.message||error).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))+'</p></body>');
    }
  });
  metaCallbackServer.listen(8765,'127.0.0.1');
  metaCallbackServer.on('error',()=>{});
}
ipcMain.handle('sales:call',(event,command,args)=>{
  if(event.sender!==window.webContents)throw new Error('Origem inválida');
  return backend(command,args);
});
ipcMain.handle('sales:openExternal', async (event, url) => {
  if(event.sender!==window.webContents) throw new Error('Origem inválida');
  const parsed=new URL(String(url));
  if(parsed.protocol!=='https:' || parsed.hostname!=='www.instagram.com') throw new Error('URL externa não autorizada');
  openInChrome(parsed.toString());
  return true;
});
function browserBounds(){
  const bounds=window.getContentBounds();
  return {x:250,y:48,width:Math.max(500,bounds.width-250),height:Math.max(300,bounds.height-48)};
}
function ensureBrowserView(){
  if(browserView&&!browserView.webContents.isDestroyed()) return browserView;
  const {BrowserView}=require('electron');
  browserView=new BrowserView({webPreferences:{contextIsolation:true,sandbox:true,partition:'persist:sales-agent-browser'}});
  browserView.webContents.setWindowOpenHandler(({url})=>({action:'allow',overrideBrowserWindowOptions:{webPreferences:{contextIsolation:true,sandbox:true,partition:'persist:sales-agent-browser'}}}));
  browserView.webContents.on('will-navigate',(event,url)=>{try{if(new URL(url).protocol!=='https:')event.preventDefault();}catch{event.preventDefault();}});
  browserView.webContents.on('destroyed',()=>{browserView=null;browserAttached=false;});
  return browserView;
}
function ensureFollowerWindow(){
  if(followerWindow&&!followerWindow.isDestroyed()) return followerWindow;
  followerWindow=new BrowserWindow({
    show:false,width:1280,height:900,skipTaskbar:true,
    webPreferences:{contextIsolation:true,sandbox:true,partition:'persist:sales-agent-browser'}
  });
  followerWindow.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  followerWindow.webContents.on('will-navigate',(event,url)=>{try{
    const parsed=new URL(url);
    if(parsed.protocol!=='https:'||!['instagram.com','www.instagram.com'].includes(parsed.hostname))event.preventDefault();
  }catch{event.preventDefault();}});
  followerWindow.on('closed',()=>{followerWindow=null;});
  return followerWindow;
}
const wait=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
async function accessibilityAction(contents,pattern,{focus=false}={}){
  const debug=contents.debugger;
  const attached=debug.isAttached();
  if(!attached)debug.attach('1.3');
  try{
    const tree=await debug.sendCommand('Accessibility.getFullAXTree');
    const candidate=(tree.nodes||[]).find(node=>node.backendDOMNodeId&&pattern.test(String(node.name?.value||''))&&(
      focus?node.role?.value==='textbox':['button','link'].includes(node.role?.value)
    ));
    if(!candidate)return false;
    const resolved=await debug.sendCommand('DOM.resolveNode',{backendNodeId:candidate.backendDOMNodeId});
    await debug.sendCommand('Runtime.callFunctionOn',{objectId:resolved.object.objectId,functionDeclaration:focus?'function(){this.focus();return document.activeElement===this}':'function(){this.click();return true}',returnByValue:true});
    return true;
  }finally{if(!attached&&debug.isAttached())debug.detach();}
}
async function conversationMessageCount(contents,text){
  const target=String(text||'').replace(/\s+/g,' ').trim();
  const debug=contents.debugger;
  const attached=debug.isAttached();
  if(!attached)debug.attach('1.3');
  try{
    const tree=await debug.sendCommand('Accessibility.getFullAXTree');
    const nodes=tree.nodes||[],byId=new Map(nodes.map(node=>[node.nodeId,node]));
    const isComposerNode=node=>{
      for(let parent=node;parent;parent=byId.get(parent.parentId))if(parent.role?.value==='textbox')return true;
      return false;
    };
    return nodes.filter(node=>!isComposerNode(node)&&String(node.name?.value||'').replace(/\s+/g,' ').trim()===target).length;
  }finally{if(!attached&&debug.isAttached())debug.detach();}
}
async function sendTextInFollowerWindow(text){
  const value=String(text||'').trim();
  const targetWindow=ensureFollowerWindow();
  const contents=targetWindow.webContents;
  if(!value)throw new Error('Mensagem de boas-vindas vazia.');
  const before=await conversationMessageCount(contents,value);
  const focused=await contents.executeJavaScript(`(()=>{
    const candidates=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')];
    const e=candidates.find(e=>/mensagem|message|responder|reply/i.test((e.getAttribute('placeholder')||'')+' '+(e.getAttribute('aria-label')||'')))||candidates.find(e=>e.matches('[contenteditable="true"],[role="textbox"]'));
    if(!e)return false;e.focus();return document.activeElement===e;
  })()`,true);
  if(!focused&&!(await accessibilityAction(contents,/mensagem|message|responder|reply/i,{focus:true})))throw new Error('Campo de mensagem do novo seguidor não encontrado.');
  contents.focus();
  clipboard.writeText(value);
  await wait(150);
  contents.sendInputEvent({type:'keyDown',keyCode:'V',modifiers:['control']});
  contents.sendInputEvent({type:'keyUp',keyCode:'V',modifiers:['control']});
  await wait(700);
  const entered=await contents.executeJavaScript(`(()=>{const e=document.activeElement;return (e?.value||e?.innerText||e?.textContent||'').trim()===${JSON.stringify(value)}})()`,true);
  if(!entered)throw new Error('A mensagem não entrou no campo do Instagram.');
  contents.sendInputEvent({type:'keyDown',keyCode:'ENTER'});
  contents.sendInputEvent({type:'keyUp',keyCode:'ENTER'});
  for(let i=0;i<12;i++){
    await wait(500);
    if(await conversationMessageCount(contents,value)>before)return {sent:true,method:'accessibility-chat-metadata'};
  }
  const error=new Error('O Instagram não confirmou a mensagem na área da conversa.');
  error.deliveryAttempted=true;
  throw error;
}
async function sendInBrowserView(text){
  const value=String(text||'').trim();
  if(!value) throw new Error('Mensagem vazia.');
  const view=ensureBrowserView();
  const url=view.webContents.getURL()||'';
  if(!url.includes('instagram.com/direct')) throw new Error('Abra uma conversa de DM do Instagram no navegador interno.');
  const countMatches=()=>view.webContents.executeJavaScript(`(()=>[...document.querySelectorAll('[role="row"],[role="listitem"],[role="article"],[role="message"]')].filter(e=>e.innerText?.trim()===${JSON.stringify(value)}).length)()`,true);
  const before=await countMatches();
  const target=await view.webContents.executeJavaScript(`(()=>{
    const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};
    const c=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);
    const e=c.find(e=>/mensagem|message|responder|reply/i.test((e.getAttribute('placeholder')||'')+' '+(e.getAttribute('aria-label')||'')))||c.find(e=>e.matches('[contenteditable="true"],[role="textbox"]'))||c.find(e=>e.tagName==='TEXTAREA'&&!/pesquis|search/i.test(e.getAttribute('placeholder')||''));
    if(!e)return null; const r=e.getBoundingClientRect(); return {x:r.left+r.width/2,y:r.top+r.height/2};
  })()`,true);
  if(!target) throw new Error('Campo de mensagem não encontrado na DM aberta.');
  view.webContents.focus();
  clipboard.writeText(value);
  view.webContents.sendInputEvent({type:'mouseDown',x:Math.round(target.x),y:Math.round(target.y),button:'left',clickCount:1});
  view.webContents.sendInputEvent({type:'mouseUp',x:Math.round(target.x),y:Math.round(target.y),button:'left',clickCount:1});
  await new Promise(r=>setTimeout(r,120));
  view.webContents.sendInputEvent({type:'keyDown',keyCode:'V',modifiers:['control']});
  view.webContents.sendInputEvent({type:'keyUp',keyCode:'V',modifiers:['control']});
  await new Promise(r=>setTimeout(r,700));
  const entered=await view.webContents.executeJavaScript(`(()=>{const e=document.activeElement;return (e?.value||e?.innerText||e?.textContent||'').trim()===${JSON.stringify(value)}})()`,true);
  if(!entered) throw new Error('O texto não foi inserido no campo da mensagem.');
  if(view.webContents.getURL()!==url) throw new Error('A conversa mudou antes do envio.');
  view.webContents.sendInputEvent({type:'keyDown',keyCode:'ENTER'});
  view.webContents.sendInputEvent({type:'keyUp',keyCode:'ENTER'});
  for(let i=0;i<10;i++){
    await new Promise(r=>setTimeout(r,500));
    if(view.webContents.getURL()!==url) throw new Error('A conversa mudou antes da confirmação do envio.');
    if(await countMatches()>before) return {sent:true,method:'mouse-paste-enter'};
  }
  // O Instagram nem sempre expõe as bolhas como nós DOM consultáveis. A
  // árvore de acessibilidade continua sendo uma confirmação confiável porque
  // é a mesma representação usada pelo navegador para exibir a conversa.
  const after=await observeBrowser();
  const delivered=after.messages.at(-1);
  if(delivered?.direction==='outgoing'&&delivered.text.trim()===value){
    return {sent:true,method:'mouse-paste-enter-accessibility'};
  }
  throw new Error('Não foi possível confirmar a mensagem na conversa.');
}
async function sendImageInBrowserView(filePath){
  const target=path.resolve(String(filePath||''));
  if(!fs.existsSync(target)||path.extname(target).toLowerCase()!=='.png')throw new Error('Pôster PNG não encontrado.');
  const view=ensureBrowserView();
  if(!(view.webContents.getURL()||'').includes('instagram.com/direct/t/'))throw new Error('Abra uma conversa de DM antes de anexar o pôster.');
  // O protocolo do navegador define o arquivo no input sem expor o sistema de
  // arquivos ao JavaScript da página.
  const debug=view.webContents.debugger;
  const attached=debug.isAttached();
  if(!attached)debug.attach('1.3');
  try{
    let document=await debug.sendCommand('DOM.getDocument',{depth:-1,pierce:true});
    let input=await debug.sendCommand('DOM.querySelector',{nodeId:document.root.nodeId,selector:'input[type="file"]'});
    if(!input.nodeId){
      const button=await view.webContents.executeJavaScript(`(()=>{const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};const all=[...document.querySelectorAll('button,[role="button"]')].filter(visible);const e=all.find(e=>/foto|photo|imagem|image|mídia|media|anexar|attach/i.test((e.getAttribute('aria-label')||'')+' '+(e.getAttribute('title')||'')));if(!e)return null;const r=e.getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2}})()`,true);
      if(!button)throw new Error('Botão de imagem não encontrado na conversa.');
      view.webContents.sendInputEvent({type:'mouseDown',x:Math.round(button.x),y:Math.round(button.y),button:'left',clickCount:1});
      view.webContents.sendInputEvent({type:'mouseUp',x:Math.round(button.x),y:Math.round(button.y),button:'left',clickCount:1});
      await new Promise(r=>setTimeout(r,500));
      document=await debug.sendCommand('DOM.getDocument',{depth:-1,pierce:true});
      input=await debug.sendCommand('DOM.querySelector',{nodeId:document.root.nodeId,selector:'input[type="file"]'});
    }
    if(!input.nodeId)throw new Error('Seletor de arquivo do Instagram não encontrado.');
    await debug.sendCommand('DOM.setFileInputFiles',{files:[target],nodeId:input.nodeId});
    await new Promise(r=>setTimeout(r,1200));
    const send=await view.webContents.executeJavaScript(`(()=>{const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};const all=[...document.querySelectorAll('button,[role="button"]')].filter(visible);const e=all.find(e=>/^(enviar|send)$/i.test((e.innerText||e.getAttribute('aria-label')||'').trim()));if(!e)return null;const r=e.getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2}})()`,true);
    if(!send)throw new Error('Botão Enviar do pôster não encontrado.');
    view.webContents.sendInputEvent({type:'mouseDown',x:Math.round(send.x),y:Math.round(send.y),button:'left',clickCount:1});
    view.webContents.sendInputEvent({type:'mouseUp',x:Math.round(send.x),y:Math.round(send.y),button:'left',clickCount:1});
    await new Promise(r=>setTimeout(r,1500));
    return {sent:true,method:'devtools-file-input',path:target};
  }finally{if(!attached&&debug.isAttached())debug.detach();}
}
ipcMain.handle('sales:browserPane', async (event, action='open', value='') => {
  if(event.sender!==window.webContents) throw new Error('Origem inválida');
  if(action==='hide'){
    browserUserVisible=false;
    if(browserView&&browserAttached){window.setBrowserView(null);browserAttached=false;}
    return {open:false,hidden:true,url:browserView?.webContents.getURL()||browserPaneUrl};
  }
  if(action==='close'){
    browserUserVisible=false;
    if(browserView){if(browserAttached)window.setBrowserView(null);browserView.webContents.close();browserView=null;browserAttached=false;}
    return {open:false};
  }
  const view=ensureBrowserView();
  browserUserVisible=true;
  if(!browserAttached){window.setBrowserView(view);browserAttached=true;}
  view.setBounds(browserBounds());
  view.setAutoResize({width:true,height:true});
  if(action==='navigate'){
    const target=new URL(String(value||browserPaneUrl));
    if(target.protocol!=='https:') throw new Error('O navegador interno aceita apenas HTTPS');
    browserPaneUrl=target.toString();
    await view.webContents.loadURL(browserPaneUrl);
  } else if(action==='home'){
    browserPaneUrl='https://www.instagram.com/direct/inbox/';
    await view.webContents.loadURL(browserPaneUrl);
  } else if(!view.webContents.getURL()) {
    await view.webContents.loadURL(browserPaneUrl);
  } else if(action==='back'&&view.webContents.canGoBack()) view.webContents.goBack();
  else if(action==='forward'&&view.webContents.canGoForward()) view.webContents.goForward();
  else if(action==='reload') view.webContents.reload();
  return {open:true,url:view.webContents.getURL()||browserPaneUrl};
});
// Leitura e interação do navegador interno. Tudo acontece no BrowserView
// persistente do próprio aplicativo; não depende de uma sessão do Chrome.
async function observeBrowser() {
  const view=ensureBrowserView();
  const url=view.webContents.getURL()||browserPaneUrl;
  if(!url.includes('instagram.com')) throw new Error('Abra o Instagram no navegador interno.');
  const snapshot=await view.webContents.executeJavaScript(`(()=>({
    url:location.href,
    title:document.title,
    threadId:(()=>{const p=location.pathname.split('/').filter(Boolean);return p.length===3&&p[0]==='direct'&&p[1]==='t'?p[2]:'';})(),
    username:(()=>{const a=[...document.querySelectorAll('a[aria-label]')].find(e=>/^(abrir a página de perfil de |open the profile page of )/i.test(e.getAttribute('aria-label')||''));const p=(a?.getAttribute('href')||'').split('/').filter(Boolean);return p.length===1&&/^[a-z0-9._]+$/i.test(p[0])?p[0]:'';})(),
    text:(document.body?.innerText||'').slice(0,30000),
    viewportWidth:window.innerWidth,
    messages:[...document.querySelectorAll('[role="message"]')].slice(-30).map(e=>{
      let parent=e, sender='';
      for(let depth=0;parent&&depth<5&&!sender;depth++,parent=parent.parentElement){
        const action=parent.querySelector('[aria-label*="mensagem de "],[aria-label*="message from "]');
        const label=action?.getAttribute('aria-label')||'';
        sender=label.match(/(?:mensagem de |message from )([^,]+)$/i)?.[1]?.trim()||'';
      }
      return {text:(e.innerText||'').trim(),sourceId:e.id||e.getAttribute('data-message-id')||'',sender};
    }),
    composer:[...document.querySelectorAll('textarea,[contenteditable="true"]')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0}).map(e=>({tag:e.tagName,aria:e.getAttribute('aria-label'),placeholder:e.getAttribute('placeholder')}))
  }))()`,true);
  if(!snapshot.messages.length){
    const debug=view.webContents.debugger;
    const attached=debug.isAttached();
    if(!attached)debug.attach('1.3');
    try{
      const tree=await debug.sendCommand('Accessibility.getFullAXTree');
      const nodes=tree.nodes||[], byId=new Map(nodes.map(n=>[n.nodeId,n]));
      const descendants=(node,depth=0)=>depth>5?[]:[node,...(node.childIds||[]).flatMap(id=>{const child=byId.get(id);return child?descendants(child,depth+1):[];})];
      snapshot.messages=await Promise.all(nodes.filter(n=>n.role?.value==='article').map(async n=>{
        let parent=byId.get(n.parentId), sender='';
        for(let i=0;parent&&i<4&&!sender;i++,parent=byId.get(parent.parentId)){
          const names=descendants(parent).map(s=>s.name?.value||'');
          const action=names.find(s=>/mensagem de |message from /i.test(s))||'';
          sender=action.match(/(?:mensagem de |message from )([^,]+)$/i)?.[1]?.trim()||'';
          if(!sender&&snapshot.username&&names.some(s=>s.toLowerCase().includes('profile page of '+snapshot.username.toLowerCase())))sender=snapshot.username;
        }
        const articleNodes=descendants(n);
        const text=n.name?.value||articleNodes.filter(s=>s.role?.value==='StaticText').map(s=>s.name?.value||'').join(' ').trim();
        const textNode=articleNodes.find(s=>s.role?.value==='StaticText'&&s.backendDOMNodeId);
        let centerX=null;
        if(textNode?.backendDOMNodeId){
          try{
            const box=await debug.sendCommand('DOM.getBoxModel',{backendNodeId:textNode.backendDOMNodeId});
            const quad=box?.model?.content||[];
            if(quad.length>=8)centerX=(quad[0]+quad[2]+quad[4]+quad[6])/4;
          }catch{}
        }
        return {text,sourceId:n.backendDOMNodeId?String(n.backendDOMNodeId):'',sender,centerX};
      }));
    }finally{if(!attached)debug.detach();}
  }
  const occurrences=new Map();
  snapshot.messages=snapshot.messages
    .map(message=>{
      const text=String(message.text||'').replace(/\s+/g,' ').trim();
      if(!text)return null;
      const sender=String(message.sender||'').trim();
      let direction='unknown';
      if(sender&&snapshot.username&&sender.toLowerCase()===snapshot.username.toLowerCase())direction='incoming';
      else if(sender)direction='incoming';
      else if(Number.isFinite(message.centerX)&&message.centerX>Number(snapshot.viewportWidth||0)*0.52)direction='outgoing';
      const signature=`${direction}\0${text}`;
      const ordinal=(occurrences.get(signature)||0)+1;
      occurrences.set(signature,ordinal);
      const id=crypto.createHash('sha256').update(`${snapshot.threadId}\0${signature}\0${ordinal}`).digest('hex');
      return {id,text,sender,direction};
    })
    .filter(Boolean)
    .slice(-40);
  return snapshot;
}
// Escolhe qualquer conversa cuja prévia termine com uma fala do contato. Isso
// inclui mensagens já lidas que ainda não receberam resposta; não depende do
// ponto azul de "não lida" do Instagram.
let inboxTabCursor=0;
async function openUnreadConversation(view){
  const diagnostics=await view.webContents.executeJavaScript(`(()=>[...document.querySelectorAll('main [role="button"], main button, [role="main"] [role="button"], [role="main"] button')].filter(e=>e.getBoundingClientRect().width>0).slice(-20).map(e=>({role:e.getAttribute('role'),aria:e.getAttribute('aria-label'),selected:e.getAttribute('aria-selected'),label:(e.innerText||'').replace(/\s+/g,' ').trim().slice(0,180),hasThreadLink:!!e.querySelector('a[href*="/direct/t/"]'),hasUnreadMarker:!!e.querySelector('[aria-label*="unread" i],[aria-label*="não lid" i]')})))()`,true);
  fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} inbox metadata ${JSON.stringify(diagnostics)}\n`);
  let choice=await view.webContents.executeJavaScript(`(()=>{
    const items=[...document.querySelectorAll('main [role="button"],main button,[role="main"] [role="button"],[role="main"] button')];
    for(const e of items){
      const r=e.getBoundingClientRect(),label=[e.getAttribute('aria-label'),e.innerText].filter(Boolean).join(' ');
      const normalized=label.replace(/\s+/g,' ').trim();
      const hasTime=/(?:agora|now|ontem|yesterday|há\s+(?:±\s*)?(?:\d+|um|uma)\s+(?:minuto|minutos|hora|horas|dia|dias)|\b\d+\s*(?:s|min|m|h|d|w))\s*$/i.test(normalized);
      const looksLikeThread=hasTime&&normalized.length>8&&!/você:|you:/i.test(normalized);
      if(!r.width||!r.height||!looksLikeThread)continue;
      const link=e.matches('a[href]')?e:e.querySelector('a[href*="/direct/t/"]');
      const path=link?new URL(link.href,location.href).pathname.split('/').filter(Boolean):[];
      e.click();
      return {clicked:true,thread:path.length===3&&path[0]==='direct'&&path[1]==='t'?path[2]:'',label:normalized.slice(0,180)};
    }return null;
  })()`,true);
  if(!choice){
    const debug=view.webContents.debugger;
    const attached=debug.isAttached();
    if(!attached)debug.attach('1.3');
    try{
      const tree=await debug.sendCommand('Accessibility.getFullAXTree');
      const timePattern=/(?:agora|now|ontem|yesterday|há\s+(?:±\s*)?(?:\d+|um|uma)\s+(?:minuto|minutos|hora|horas|dia|dias)|\b\d+\s*(?:s|min|m|h|d|w))\s*$/i;
      const candidate=(tree.nodes||[]).find(node=>{
        const label=String(node.name?.value||'');
        return node.role?.value==='button'&&node.backendDOMNodeId&&label.length>8&&timePattern.test(label.replace(/\s+/g,' ').trim())&&!/você:|you:/i.test(label);
      });
      if(candidate){
        await debug.sendCommand('DOM.resolveNode',{backendNodeId:candidate.backendDOMNodeId}).then(async resolved=>{
          await debug.sendCommand('Runtime.callFunctionOn',{objectId:resolved.object.objectId,functionDeclaration:'function(){this.click()}',returnByValue:true});
        });
        choice={clicked:true,thread:'',label:String(candidate.name?.value||'').slice(0,180)};
      }
    }finally{if(!attached)debug.detach();}
  }
  if(!choice){
    // O Instagram separa o inbox em Primary, General e Pedidos. Quando a aba
    // atual não contém uma fala pendente, percorremos as demais em vez de
    // ficar presos para sempre na Primary.
    const switched=await view.webContents.executeJavaScript(`(()=>{const tabs=[...document.querySelectorAll('[role="tab"]')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0});if(tabs.length<2)return false;const index=${inboxTabCursor++}%tabs.length;tabs[index].click();return (tabs[index].innerText||tabs[index].getAttribute('aria-label')||String(index)).trim()})()`,true);
    if(switched)fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} inbox tab ${switched}\n`);
    return false;
  }
  fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} inbox opening ${JSON.stringify(choice)}\n`);
  for(let i=0;i<12;i++){
    await new Promise(r=>setTimeout(r,500));
    const parts=new URL(view.webContents.getURL()).pathname.split('/').filter(Boolean);
    if(parts.length===3&&parts[0]==='direct'&&parts[1]==='t'&&(!choice.thread||parts[2]===choice.thread))return true;
  }
  fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} inbox open not confirmed ${JSON.stringify(choice)}\n`);
  return false;
}
ipcMain.handle('sales:browserObserve', async (event) => {
  if(event.sender!==window.webContents) throw new Error('Origem inválida');
  return observeBrowser();
});
ipcMain.handle('sales:importBrowserInbox', async (event) => {
  if(event.sender!==window.webContents) throw new Error('Origem inválida');
  const view=ensureBrowserView();
  const current=view.webContents.getURL()||'';
  if(!current.includes('instagram.com')) throw new Error('Entre no Instagram pelo navegador interno antes de importar as DMs.');
  if(!current.includes('/direct/inbox')){
    await view.webContents.loadURL('https://www.instagram.com/direct/inbox/');
    await wait(1200);
  }
  const links=await view.webContents.executeJavaScript(`(()=>[...new Set([...document.querySelectorAll('a[href*="/direct/t/"]')].map(a=>a.href).filter(href=>/^https:\/\/(?:www\.)?instagram\.com\/direct\/t\/[^/?#]+\/?/i.test(href)))].slice(0,80))()`,true);
  if(!links.length) throw new Error('Não encontrei conversas acessíveis na caixa de entrada. Abra a caixa de entrada do Instagram e aguarde a lista carregar.');
  let imported=0, messages=0, skipped=0;
  for(const href of links){
    try{
      await view.webContents.loadURL(href);
      await wait(650);
      const snapshot=await observeBrowser();
      if(!snapshot.threadId||!snapshot.username||!snapshot.messages.length){skipped++;continue;}
      const result=await backend('browserImportThread',{thread_id:snapshot.threadId,username:snapshot.username,messages:snapshot.messages});
      imported++;messages+=Number(result.stored||0);
    }catch{skipped++;}
  }
  await view.webContents.loadURL('https://www.instagram.com/direct/inbox/');
  return {threads:imported,messages,skipped};
});
ipcMain.handle('sales:scanFeedProfiles', async (event) => {
  if(event.sender!==window.webContents) throw new Error('Origem inválida');
  const view=ensureBrowserView();const url=view.webContents.getURL()||'';
  if(!url.includes('instagram.com')) throw new Error('Abra o feed do Instagram no navegador interno antes de procurar perfis.');
  const usernames=new Set();
  for(let pass=0;pass<3;pass++){
    const visible=await view.webContents.executeJavaScript(`(()=>{
      const reserved=new Set(['accounts','direct','explore','reels','stories','about','developer','legal','privacy','web','p']);
      return [...new Set([...document.querySelectorAll('a[href]')].map(a=>{const parts=new URL(a.href,location.href).pathname.split('/').filter(Boolean);return parts.length===1&&!reserved.has(parts[0])?parts[0].toLowerCase():''}).filter(Boolean))].slice(0,30);
    })()`,true);
    visible.forEach(username=>usernames.add(username));
    if(pass<2){await view.webContents.executeJavaScript('window.scrollBy({top:Math.max(560,innerHeight*.82),behavior:"smooth"});true',true);await wait(900);}
  }
  const pageText=await view.webContents.executeJavaScript('document.body?.innerText?.slice(0,5000)||""',true);
  const candidates=[...usernames].slice(0,45).map(username=>({username,text:pageText,following:false}));
  const result=await backend('campaignDiscover',{profiles:candidates});
  return {...result,scanned:candidates.length};
});
ipcMain.handle('sales:browserSend', async (event, text='') => {
  if(event.sender!==window.webContents) throw new Error('Origem inválida');
  const state=await backend('agentStatus');
  if(!state.active) throw new Error('Ative o agente de vendas antes do envio automático.');
  const result=await sendInBrowserView(text);
  fs.mkdirSync(app.getPath('userData'),{recursive:true});
  fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} ${JSON.stringify(result)}\n`);
  return result;
});
let processing=false;
const replyTimer=setInterval(async()=>{},5000);
replyTimer.unref();
let browserProcessing=false;
let followerScanRequested=false;
let lastFollowerScanAt=0;
async function scanInstagramHome(view){
  /* A página inicial mantém os contadores como texto acessível; não depende
     de pixels, nem de a caixa de entrada já estar visível. */
  const indicators=await view.webContents.executeJavaScript(`(()=>{
    const nodes=[...document.querySelectorAll('a,button,[role="link"],[role="button"]')];
    const match=(pattern)=>nodes.filter(node=>pattern.test(((node.innerText||'')+' '+(node.getAttribute('aria-label')||'')+' '+(node.getAttribute('title')||'')+' '+(node.getAttribute('href')||'')).replace(/\\s+/g,' ').trim())).map(node=>({text:(node.innerText||node.getAttribute('aria-label')||node.getAttribute('href')||'').trim().slice(0,140),href:node.href||'',badge:(node.innerText||'').match(/\\b\\d+\\b/)?.[0]||''}));
    const notifications=match(/notifica(?:ç|c)(?:ões|oes)|notifications|activity/i);
    // O contador novo do Instagram pode ser apenas uma bolinha vermelha, sem
    // texto nem aria-label. Detecte-a dentro do botão/link de notificações.
    const redBadge=notifications.some(item=>{
      const host=nodes.find(node=>(node.href||'')===item.href||((node.innerText||node.getAttribute('aria-label')||node.getAttribute('href')||'')+' '+(node.getAttribute('title')||'')).replace(/\s+/g,' ').trim()===item.text);
      if(!host)return false;
      return [...host.querySelectorAll('*')].some(child=>{
        const style=getComputedStyle(child),rect=child.getBoundingClientRect();
        const color=String(style.backgroundColor||'');
        return rect.width>3&&rect.width<28&&rect.height>3&&rect.height<28&&/rgb\(2(?:[0-5][0-9]|[0-4][0-9]),\s*(?:[0-9]{1,2}|1[0-3][0-9]),\s*(?:[0-9]{1,2}|1[0-3][0-9])\)/.test(color);
      });
    });
    return {messages:match(/mensagens|messages|direct/i),notifications,redBadge};
  })()`,true);
  const hasMessage=indicators.messages.some(item=>item.badge||/nova|new|unread|não lida/i.test(item.text));
  const hasNotification=Boolean(indicators.redBadge)||indicators.notifications.some(item=>item.badge||/nova|new/i.test(item.text));
  fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} home indicators ${JSON.stringify({hasMessage,hasNotification,indicators})}\n`);
  if(hasMessage){
    await view.webContents.loadURL('https://www.instagram.com/direct/inbox/');
    return {openedInbox:true,hasNotification};
  }
  return {openedInbox:false,hasNotification};
}
function isInstagramAuthenticationPage(url){
  try{
    const parsed=new URL(url);
    if(!/(^|\.)instagram\.com$/i.test(parsed.hostname)) return false;
    const path=parsed.pathname.toLowerCase();
    return path.startsWith('/accounts/login')||path.startsWith('/accounts/signup')||path.startsWith('/accounts/password')||path.startsWith('/challenge')||path.startsWith('/checkpoint')||path.startsWith('/two_factor_authentication');
  }catch{return false;}
}
async function isInstagramAuthenticationScreen(view,url){
  if(isInstagramAuthenticationPage(url))return true;
  try{
    return await view.webContents.executeJavaScript(`(()=>{
      const fields=[...document.querySelectorAll('input,textarea,[contenteditable="true"]')];
      return fields.some(field=>{
        const text=[field.name,field.type,field.autocomplete,field.placeholder,field.getAttribute('aria-label')].filter(Boolean).join(' ').toLowerCase();
        return /username|senha|password|one-time-code|verification|security code|c[oó]digo/.test(text);
      });
    })()`,true);
  }catch{return false;}
}
const browserTimer=setInterval(async()=>{
  if(browserProcessing||!window||window.isDestroyed())return;
  browserProcessing=true;
  try{
    fs.mkdirSync(app.getPath('userData'),{recursive:true}); fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} tick\n`);
    const activeView=ensureBrowserView();
    const state=await backend('agentStatus');
    let url=activeView.webContents.getURL()||'';
    if(state.active&&!url){await activeView.webContents.loadURL('https://www.instagram.com/');url=activeView.webContents.getURL()||'';}
    if(!state.active)return;
    // Nunca interrompa a autenticação manual. Enquanto a página de login,
    // desafio ou checkpoint estiver aberta, o operador controla a tela e o
    // ciclo aguarda o Instagram concluir a sessão por conta própria.
    if(await isInstagramAuthenticationScreen(activeView,url))return;
    if(url.includes('instagram.com/')&&!url.includes('instagram.com/direct')){
      const home=await scanInstagramHome(activeView);
      if(home.hasNotification)followerScanRequested=true;
      // O contador do Instagram nem sempre fica exposto na árvore de
      // acessibilidade. Depois da leitura da página inicial, entre no inbox
      // também quando não houver contador legível: assim a lista de DMs é a
      // fonte de confirmação e nenhuma conversa pendente fica invisível.
      if(!home.openedInbox){
        await activeView.webContents.loadURL('https://www.instagram.com/direct/inbox/');
      }
      url=activeView.webContents.getURL()||'';
    }
    if(!url.includes('instagram.com/direct'))return;
    if(new URL(url).pathname.startsWith('/direct/inbox')){await openUnreadConversation(activeView);return;}
    const snap=await observeBrowser();
    const last=snap.messages.at(-1);
    fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} message metadata ${JSON.stringify({thread:!!snap.threadId,username:!!snap.username,count:snap.messages.length,hasId:!!last?.id,direction:last?.direction||'none'})}\n`);
    if(!snap.threadId||!snap.username||!last?.id||!last.text||last.direction!=='incoming'){
      await activeView.webContents.loadURL('https://www.instagram.com/direct/inbox/');
      return;
    }
    const cycle=await backend('browserScreenCycle',{url:snap.url,thread_id:snap.threadId,username:snap.username,message_id:last.id,message:last.text,direction:'incoming',messages:snap.messages});
    if(cycle?.new_message&&cycle.text){
      await new Promise(r=>setTimeout(r,3500));
      if(!(await backend('agentStatus')).active||activeView.webContents.getURL()!==snap.url)return;
      if(cycle.competitor?.asset_ready){
        try{
          const imageResult=await sendImageInBrowserView(cycle.competitor.asset_path);
          fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} poster ${JSON.stringify({competitor:cycle.competitor.slug,...imageResult})}\n`);
        }catch(error){
          fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} poster-error ${cycle.competitor.slug} ${error.message}\n`);
        }
      }
      await sendInBrowserView(cycle.text);
      await backend('browserScreenConfirm',{message_key:cycle.message_key,lead_id:cycle.lead_id,text:cycle.text,thread_id:snap.threadId});
    }
    await activeView.webContents.loadURL('https://www.instagram.com/direct/inbox/');
  }catch(error){try{fs.mkdirSync(app.getPath('userData'),{recursive:true});fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} error ${error.message}\n`);}catch{}} finally{browserProcessing=false;}
},8000);
browserTimer.unref();
function followerLog(message){
  try{
    fs.mkdirSync(app.getPath('userData'),{recursive:true});
    fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} follower ${message}\n`);
  }catch{}
}
async function findFollowerNotification(contents){
  return contents.executeJavaScript(`(()=>{
    const reserved=new Set(['accounts','direct','explore','reels','stories','about','developer','legal','privacy','web']);
    const visible=e=>!!e;
    const parts=[...document.querySelectorAll('span,div,p')].filter(e=>{
      const text=(e.innerText||'').replace(/\s+/g,' ').trim();
      return text.length>0&&text.length<320&&/(começou a seguir você|started following you)/i.test(text);
    }).sort((a,b)=>(a.innerText||'').length-(b.innerText||'').length);
    for(const part of parts){
      let row=part;
      for(let depth=0;row&&depth<9;depth++,row=row.parentElement){
        const anchors=[...row.querySelectorAll('a[href]')];
        const profile=anchors.map(a=>({a,path:new URL(a.href,location.href).pathname.split('/').filter(Boolean)}))
          .find(item=>item.path.length===1&&/^[a-z0-9._]{1,30}$/i.test(item.path[0])&&!reserved.has(item.path[0].toLowerCase()));
        if(!profile)continue;
        const actions=[...row.querySelectorAll('button,[role="button"]')].filter(visible);
        const follow=actions.find(e=>/^(seguir de volta|follow back|seguir|follow)$/i.test((e.innerText||e.getAttribute('aria-label')||'').trim()));
        return {username:profile.path[0].toLowerCase(),hasFollowButton:!!follow,text:(row.innerText||'').replace(/\s+/g,' ').trim().slice(0,300)};
      }
      // Na interface atual o nome e o texto da notificação podem ficar em
      // ramos DOM irmãos. A linha visual continua sendo inequívoca: escolhe o
      // link de perfil mais próximo no eixo vertical.
      const partRect=part.getBoundingClientRect();
      const nearby=[...document.querySelectorAll('a[href]')].filter(visible).map(a=>{
        const path=new URL(a.href,location.href).pathname.split('/').filter(Boolean);
        const rect=a.getBoundingClientRect();
        return {path,distance:Math.abs((rect.top+rect.height/2)-(partRect.top+partRect.height/2))};
      }).filter(item=>item.path.length===1&&/^[a-z0-9._]{1,30}$/i.test(item.path[0])&&!reserved.has(item.path[0].toLowerCase()))
        .sort((a,b)=>a.distance-b.distance)[0];
      if(nearby&&nearby.distance<140)return {username:nearby.path[0].toLowerCase(),hasFollowButton:false,text:(part.innerText||'').replace(/\s+/g,' ').trim().slice(0,300)};
    }
    const sample=parts.slice(0,3).map(part=>{
      const rect=part.getBoundingClientRect();
      const links=[...document.querySelectorAll('a[href]')].filter(visible).map(a=>{
        const r=a.getBoundingClientRect();
        return {label:(a.innerText||a.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim().slice(0,80),href:new URL(a.href,location.href).pathname,distance:Math.round(Math.abs((r.top+r.height/2)-(rect.top+rect.height/2)))};
      }).filter(a=>a.distance<220).slice(0,8);
      return {text:(part.innerText||'').replace(/\s+/g,' ').trim().slice(0,220),links};
    });
    return {username:'',diagnostic:sample};
  })()`,true);
}
async function findFollowerFromAccessibility(contents){
  const debug=contents.debugger;
  const attached=debug.isAttached();
  if(!attached)debug.attach('1.3');
  try{
    const tree=await debug.sendCommand('Accessibility.getFullAXTree');
    const nodes=tree.nodes||[],byId=new Map(nodes.map(node=>[node.nodeId,node]));
    const descendants=(node,depth=0)=>depth>8?[]:[node,...(node.childIds||[]).flatMap(id=>{const child=byId.get(id);return child?descendants(child,depth+1):[];})];
    const extractUsername=name=>{
      const text=String(name||'').trim();
      const matched=text.match(/(?:foto do perfil de |profile photo of )?([a-z0-9._]{1,30})$/i);
      return matched?matched[1].toLowerCase():'';
    };
    for(const marker of nodes.filter(node=>/(começou a seguir você|started following you)/i.test(String(node.name?.value||'')))){
      let parent=byId.get(marker.parentId);
      for(let depth=0;parent&&depth<10;depth++,parent=byId.get(parent.parentId)){
        const username=descendants(parent).filter(node=>node.role?.value==='link').map(node=>extractUsername(node.name?.value)).find(Boolean);
        if(username)return {username,source:'accessibility'};
      }
    }
    return null;
  }finally{if(!attached&&debug.isAttached())debug.detach();}
}
async function openFollowerNotifications(contents){
  // A interface atual do Instagram redireciona /accounts/activity para
  // /notifications. Use a rota vigente para evitar uma navegação extra.
  await contents.loadURL('https://www.instagram.com/notifications/');
  await wait(2200);
  let state=await contents.executeJavaScript(`(()=>({url:location.href,hasFollowerText:/(começou a seguir você|started following you)/i.test(document.body?.innerText||'')}))()`,true);
  if(state.hasFollowerText)return {...state,opened:false};
  const opened=await contents.executeJavaScript(`(()=>{
    const elements=[...document.querySelectorAll('a,button,[role="link"],[role="button"],[aria-label]')];
    const exact=elements.find(e=>/^(notificações|notifications)$/i.test((e.getAttribute('aria-label')||e.innerText||'').replace(/\s+/g,' ').trim()));
    const route=elements.find(e=>(e.getAttribute('href')||'').includes('/accounts/activity'));
    const target=exact||route;
    if(!target)return false;(target.closest('a,button,[role="link"],[role="button"]')||target).click();return true;
  })()`,true);
  if(opened)await wait(1800);
  state=await contents.executeJavaScript(`(()=>({url:location.href,hasFollowerText:/(começou a seguir você|started following you)/i.test(document.body?.innerText||'')}))()`,true);
  return {...state,opened};
}
async function followAndOpenMessage(contents,username,openMessage=true){
  const followed=await contents.executeJavaScript(`(()=>{
    const wanted=${JSON.stringify(String(username).toLowerCase())};
    const visible=e=>!!e;
    const link=[...document.querySelectorAll('a[href]')].find(a=>new URL(a.href,location.href).pathname.split('/').filter(Boolean).join('/').toLowerCase()===wanted);
    if(!link)return false;
    let row=link;
    for(let depth=0;row&&depth<9;depth++,row=row.parentElement){
      const button=[...row.querySelectorAll('button,[role="button"]')].filter(visible).find(e=>/^(seguir de volta|follow back|seguir|follow)$/i.test((e.innerText||e.getAttribute('aria-label')||'').trim()));
      if(button){button.click();return true;}
    }
    return false;
  })()`,true);
  if(followed)await wait(1400);
  await contents.loadURL(`https://www.instagram.com/${encodeURIComponent(username)}/`);
  await wait(1800);
  const followedOnProfile=await contents.executeJavaScript(`(()=>{
    const button=[...document.querySelectorAll('button,[role="button"]')].find(e=>/^(seguir de volta|follow back|seguir|follow)$/i.test((e.innerText||e.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim()));
    if(!button)return false;button.click();return true;
  })()`,true);
  if(followedOnProfile)await wait(1200);
  const profile=await contents.executeJavaScript(`(()=>({
    username:${JSON.stringify(String(username).toLowerCase())},
    name:(document.querySelector('header h1,header h2,h1,h2')?.innerText||'').trim().slice(0,180),
    bio:(document.body?.innerText||'').replace(/\s+/g,' ').slice(0,5000),
    text:(document.body?.innerText||'').replace(/\s+/g,' ').slice(0,5000)
  }))()`,true);
  if(!openMessage)return {followed:followed||followedOnProfile,profile};
  const opened=await contents.executeJavaScript(`(()=>{
    const elements=[...document.querySelectorAll('button,[role="button"],a')];
    const button=elements.find(e=>/^(mensagem|message|enviar mensagem|send message)$/i.test((e.innerText||e.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim()));
    if(!button)return false;button.click();return true;
  })()`,true);
  if(!opened&&!(await accessibilityAction(contents,/^(mensagem|message|enviar mensagem|send message)$/i)))throw new Error('Botão Mensagem não encontrado no perfil @'+username+'.');
  for(let i=0;i<30;i++){
    await wait(500);
    const ready=await contents.executeJavaScript(`(()=>[...document.querySelectorAll('textarea,[contenteditable="true"],[role="textbox"]')].some(e=>/mensagem|message|responder|reply/i.test((e.getAttribute('placeholder')||'')+' '+(e.getAttribute('aria-label')||''))))()`,true);
    if(ready||await accessibilityAction(contents,/mensagem|message|responder|reply/i,{focus:true}))return {followed:followed||followedOnProfile,messageOpened:true,profile};
  }
  throw new Error('A conversa de @'+username+' não abriu.');
}
let followerProcessing=false;
const followerTimer=setInterval(async()=>{
  if(followerProcessing||!app.isReady()||!window||window.isDestroyed())return;
  const now=Date.now();
  // O timer normal evita custo desnecessário. Uma bolinha detectada na página
  // inicial concede prioridade à próxima execução em vez de esperar o ciclo
  // longo da leitura de notificações.
  if(!followerScanRequested&&now-lastFollowerScanAt<45000)return;
  followerProcessing=true;
  followerScanRequested=false;
  lastFollowerScanAt=now;
  let claimedUsername='';
  try{
    const state=await backend('agentStatus');
    if(!state.active)return;
    const followerView=ensureFollowerWindow();
    const contents=followerView.webContents;
    const notificationState=await openFollowerNotifications(contents);
    followerLog(`scan ${JSON.stringify(notificationState)}`);
    let candidate=await findFollowerNotification(contents);
    if(!candidate?.username)candidate=await findFollowerFromAccessibility(contents)||candidate;
    if(!candidate?.username){followerLog(`unresolved ${JSON.stringify(candidate||{})}`);return;}
    const inspection=await followAndOpenMessage(contents,candidate.username,false);
    const cycle=await backend('followerCycle',{username:candidate.username,profile:inspection.profile});
    if(!cycle?.new_follower)return;
    claimedUsername=candidate.username;
    followerLog(`detected @${claimedUsername}`);
    await followAndOpenMessage(contents,claimedUsername,true);
    await wait(3500);
    if(!(await backend('agentStatus')).active)throw new Error('Agente desativado antes da mensagem.');
    const sent=await sendTextInFollowerWindow(cycle.text);
    await backend('followerConfirm',{username:claimedUsername});
    followerLog(`completed @${claimedUsername} ${JSON.stringify(sent)}`);
  }catch(error){
    followerLog(`error ${claimedUsername?'@'+claimedUsername+' ':''}${error.message}`);
    if(claimedUsername&&error.deliveryAttempted){
      followerLog(`pending-confirmation @${claimedUsername}; envio bloqueado para evitar duplicação`);
    }else if(claimedUsername)await backend('followerReset',{username:claimedUsername}).catch(()=>null);
  }finally{followerProcessing=false;}
},8000);
followerTimer.unref();
// Supervisor autônomo: inicia as IAs e serviços locais ao abrir e recupera-os
// se algum processo parar. O produto não depende do Codex em runtime.
const serviceTimer=setInterval(()=>backend('startServices').catch(error=>{
  try{fs.appendFileSync(path.join(app.getPath('userData'),'desktop.log'),`${new Date().toISOString()} supervisor ${error.message}\n`);}catch{}
}),60000);
serviceTimer.unref();
function record(error) {
  const message = error?.stack || String(error);
  fs.mkdirSync(app.getPath('userData'), {recursive:true});
  fs.appendFileSync(path.join(app.getPath('userData'), 'desktop.log'), `${new Date().toISOString()} ${message}\n`);
  dialog.showErrorBox('Agente de Vendas Local', message);
}
if (!app.requestSingleInstanceLock()) app.quit();
else {
  // O atalho pode ser acionado enquanto o Electron ainda descarrega uma
  // janela anterior. Não tente restaurar um BrowserWindow já destruído.
  app.on('second-instance', () => {
    if(!window||window.isDestroyed()) return;
    if(window.isMinimized()) window.restore();
    window.focus();
  });
  app.whenReady().then(async () => {
    startMetaCallbackServer();
    // O supervisor sobe os serviços locais em paralelo. A janela não deve
    // esperar tentativas de conexão com Ollama/BrowserOS para ficar utilizável.
    backend('startServices').catch(()=>null);
    window = new BrowserWindow({width:1660,height:980,minWidth:1000,minHeight:700,title:'Agente de Vendas Local',backgroundColor:'#07111f',autoHideMenuBar:true,show:true,webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true}});
    window.webContents.setWindowOpenHandler(() => ({action:'deny'}));
    window.webContents.on('will-navigate', (event, url) => {if(!url.startsWith('file:')) event.preventDefault();});
    window.once('ready-to-show', () => window.show());
    window.on('resize',()=>{if(browserAttached&&browserView&&!browserView.webContents.isDestroyed())browserView.setBounds(browserBounds());});
    await window.loadFile(path.join(__dirname,'..','frontend','index.html'));
    // O navegador interno é a ferramenta principal do agente: já abre
    // exposto no Instagram para o operador iniciar ou acompanhar interações.
    const initialBrowser=ensureBrowserView();
    browserUserVisible=true;
    window.setBrowserView(initialBrowser);
    browserAttached=true;
    initialBrowser.setBounds(browserBounds());
    initialBrowser.setAutoResize({width:true,height:true});
    if(!initialBrowser.webContents.getURL()) await initialBrowser.webContents.loadURL(browserPaneUrl);
    if(process.argv.includes('--smoke-test')) {
      const result = await window.webContents.executeJavaScript(`(async()=>{const leads=await window.sales.call('leads');const templates=await window.sales.call('responseLibrary');const libraryButton=document.querySelector('[data-view="library"]');libraryButton.click();await new Promise(resolve=>setTimeout(resolve,300));const operatorButton=document.querySelector('[data-view="operator"]');return {title:document.title,backend:true,leads:leads.length,templates:templates.length,libraryForm:!!document.querySelector('#template-form'),operatorAvailable:!!operatorButton};})()`);
      fs.writeFileSync(path.join(app.getPath('userData'),'smoke-test.json'),JSON.stringify(result));
      app.quit();
    }
  }).catch(record);
  app.on('window-all-closed',()=>{window=null;app.quit();});
  app.on('will-quit',()=>{if(metaCallbackServer)metaCallbackServer.close();if(followerWindow&&!followerWindow.isDestroyed())followerWindow.destroy();if(backendChild&&!backendChild.killed)backendChild.kill();if(remoteTunnelChild&&!remoteTunnelChild.killed)remoteTunnelChild.kill();if(localLlmChild&&!localLlmChild.killed)localLlmChild.kill();});
}
process.on('uncaughtException', record);
