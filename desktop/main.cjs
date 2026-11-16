const {app, BrowserWindow, dialog, ipcMain, shell, session} = require('electron');
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
let browserLoadError='';
let metaCallbackServer;
let backendChild=null;
let backendBuffer='';
let backendSequence=0;
const backendPending=new Map();
let localLlmChild=null;
let remoteTunnelChild=null;
let remoteTunnelStartedAt=0;
const localLlmPort=11535;
function persistentAgentDataDir(){
  // app.getPath('userData') pertence ao perfil real do Electron. Derivar a
  // pasta Local dele evita que um launcher/sandbox substitua LOCALAPPDATA e
  // faça o backend abrir um banco temporário, perdendo o estado do agente.
  const userData=app.getPath('userData');
  const appData=path.dirname(path.dirname(userData));
  return path.join(appData,'Local','SalesAgentLocal');
}
function remoteControlConfig(){
  const candidates=[path.join(process.resourcesPath,'remote-control.json'),path.join(app.getPath('userData'),'remote-control.json')];
  for(const file of candidates){try{const config=JSON.parse(fs.readFileSync(file,'utf8'));if(config?.enabled&&config?.sshHost)return config;}catch{}}
  return null;
}
const remoteControl=remoteControlConfig();
const isRemoteControl=Boolean(remoteControl);
const sessionExportArg=process.argv.find(value=>String(value).startsWith('--export-vps-session='));
const sessionExportPath=sessionExportArg?path.resolve(String(sessionExportArg).slice('--export-vps-session='.length)):'';
function isSessionHost(domain){const host=String(domain||'').replace(/^\./,'').toLowerCase();return host==='instagram.com'||host.endsWith('.instagram.com')||host==='facebook.com'||host.endsWith('.facebook.com');}
async function exportPersistentBrowserSession(destination){
  if(!destination)throw new Error('Destino de exportação não informado.');
  const cookies=(await session.fromPartition('persist:sales-agent-browser').cookies.get({})).filter(cookie=>isSessionHost(cookie.domain));
  if(!cookies.some(cookie=>String(cookie.name)==='sessionid'&&String(cookie.domain).includes('instagram.com')))throw new Error('A sessão do Instagram ainda não está disponível para migração.');
  const payload={version:1,created_at:new Date().toISOString(),cookies};
  fs.mkdirSync(path.dirname(destination),{recursive:true});
  const temporary=destination+'.tmp';
  fs.writeFileSync(temporary,JSON.stringify(payload),{mode:0o600});
  fs.renameSync(temporary,destination);
  return {cookies:cookies.length};
}
function startRemoteTunnel(){
  if(!remoteControl||(remoteTunnelChild&&!remoteTunnelChild.killed))return;
  const executable=process.env.WINDIR?path.join(process.env.WINDIR,'System32','OpenSSH','ssh.exe'):'ssh';
  const port=String(remoteControl.localPort||8787);
  remoteTunnelStartedAt=Date.now();
  remoteTunnelChild=spawn(executable,['-N','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=30','-o','ServerAliveCountMax=3','-L',`${port}:127.0.0.1:${remoteControl.remotePort||8787}`,remoteControl.sshHost],{windowsHide:true,stdio:['ignore','ignore','pipe']});
  remoteTunnelChild.stderr?.on('data',data=>{
    try{fs.appendFileSync(path.join(app.getPath('userData'),'desktop.log'),`${new Date().toISOString()} remote-tunnel ${String(data).slice(0,800)}\n`);}catch{}
  });
  remoteTunnelChild.on('error',error=>{try{fs.appendFileSync(path.join(app.getPath('userData'),'desktop.log'),`${new Date().toISOString()} remote-tunnel-error ${error.message}\n`);}catch{}});
  remoteTunnelChild.on('close',(code)=>{
    try{fs.appendFileSync(path.join(app.getPath('userData'),'desktop.log'),`${new Date().toISOString()} remote-tunnel-closed code=${code}\n`);}catch{}
    remoteTunnelChild=null;
  });
}
function remoteBackend(command,args={}){return new Promise((resolve,reject)=>{
  startRemoteTunnel();
  const body=Buffer.from(JSON.stringify({id:++backendSequence,command,args}));
  const deadline=Date.now()+9000;
  const dispatch=()=>{
    const request=http.request({hostname:'127.0.0.1',port:remoteControl.localPort||8787,path:'/api/rpc',method:'POST',headers:{'Content-Type':'application/json','Content-Length':body.length},timeout:120000},response=>{let raw='';response.on('data',part=>raw+=part);response.on('end',()=>{try{const payload=JSON.parse(raw);payload.ok?resolve(payload.result):reject(new Error(payload.error||'Falha do agente na VPS.'));}catch{reject(new Error('Resposta inválida do agente na VPS.'));}});});
    request.on('timeout',()=>request.destroy(new Error('A VPS demorou para responder.')));
    request.on('error',error=>{
      if(error.code==='ECONNREFUSED'&&Date.now()<deadline){startRemoteTunnel();setTimeout(dispatch,350);return;}
      reject(new Error(`Controle remoto indisponível: ${error.message}`));
    });
    request.write(body);request.end();
  };
  dispatch();
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
const backendAllowed=['leads','create','messages','message','draft','queue','pause','followup','knowledge','saveKnowledge','responseLibrary','saveResponseTemplate','saveTrialOffer','browserImportThread','classifyImportedHistory','campaignDiscover','campaignClaim','campaignConfirm','followupRecords','completeFollowup','status','records','syncHistory','syncPostflow','analytics','saveDocument','ragContext','comparison','competitorCatalog','competitorMatch','competitorSeed','research','personality','probabilities','trial','outcome','installation','approveReply','dispatchDue','agentCycle','agentStatus','setAgentActive','setProspectingActive','prospectingPacing','followerCycle','followerConfirm','followerReset','startServices','browserScreenCycle','browserScreenConfirm','browserScreenReset','replyDelay','postflowStatus','postflowIngestionStatus','metaStatus','metaOAuthUrl','metaOAuthExchange','browserHealth','browserTools','browserSnapshot','browserAct','browserInstagramInbox','browserRead','internalBrowserStatus','internalBrowserSnapshot','internalBrowserVisualState','internalBrowserScreenshot','internalBrowserAction'];
backendAllowed.push('internalBrowserImportSession','internalBrowserMetadata','browserNotificationCandidate');
function ensureBackend(){
  if(backendChild&&!backendChild.killed)return backendChild;
  const root=path.join(__dirname,'..');
  const packaged=path.join(process.resourcesPath,'SalesAgentBackend.exe');
  const embedded=startEmbeddedLlm();
  const env={...metaVaultEnv(),SALES_AGENT_RPC_STREAM:'1',SALES_AGENT_DATA_DIR:persistentAgentDataDir(),...(embedded?{LOCAL_LLM_URL:`http://127.0.0.1:${localLlmPort}`,LOCAL_LLM_MODEL:'qwen3-sales'}:{})};
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
  // O BrowserView é uma camada nativa acima do HTML. Ele não pode começar no
  // topo, pois esconderia o cabeçalho do painel (inclusive os controles de
  // ativação e pausa). A faixa deixa espaço para título, busca e botões,
  // mesmo quando a janela estiver menor e o cabeçalho ocupar duas linhas.
  const headerHeight=126;
  return {x:250,y:headerHeight,width:Math.max(500,bounds.width-250),height:Math.max(300,bounds.height-headerHeight)};
}
function ensureBrowserView(){
  if(browserView&&!browserView.webContents.isDestroyed()) return browserView;
  const {BrowserView}=require('electron');
  browserView=new BrowserView({webPreferences:{contextIsolation:true,sandbox:true,partition:'persist:sales-agent-browser'}});
  browserView.webContents.setWindowOpenHandler(({url})=>({action:'allow',overrideBrowserWindowOptions:{webPreferences:{contextIsolation:true,sandbox:true,partition:'persist:sales-agent-browser'}}}));
  browserView.webContents.on('will-navigate',(event,url)=>{try{if(new URL(url).protocol!=='https:')event.preventDefault();}catch{event.preventDefault();}});
  // A indisponibilidade transitória do Instagram não pode derrubar o painel
  // nem abrir uma caixa de erro fatal no controlador remoto.
  browserView.webContents.on('did-fail-load',(_event,errorCode,errorDescription,validatedURL,isMainFrame)=>{
    if(!isMainFrame)return;
    browserLoadError=`${errorCode}: ${String(errorDescription||'falha ao carregar').slice(0,120)}`;
    try{fs.mkdirSync(app.getPath('userData'),{recursive:true});fs.appendFileSync(path.join(app.getPath('userData'),'desktop.log'),`${new Date().toISOString()} browser-load ${browserLoadError} ${validatedURL}\n`);}catch{}
  });
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
const AGENT_BUBBLE_SEPARATOR='\n[[AGENT_BUBBLE]]\n';
function interactionDie(){return crypto.randomInt(1,7);}
async function typeWithVirtualKeyboard(contents,value,label='message'){
  // Eventos `char` são o teclado virtual do BrowserView. Não usamos área de
  // transferência: cada caractere é inserido com uma pequena variação humana.
  let totalDelay=0; const rolls=[];
  for(const character of Array.from(String(value))){
    const die=interactionDie(); rolls.push(die);
    contents.sendInputEvent({type:'char',keyCode:character});
    const delay=18+(die*13)+crypto.randomInt(0,24);
    totalDelay+=delay;
    await wait(delay);
  }
  return {method:'virtual-keyboard',characters:Array.from(String(value)).length,total_delay_ms:totalDelay,dice:rolls};
}
async function naturalInteractionPause(label,minMs=1800,maxMs=6000){
  const die=interactionDie();
  const span=Math.max(0,maxMs-minMs);
  const delay=Math.min(maxMs,minMs+Math.floor((die/6)*span)+crypto.randomInt(0,Math.max(1,Math.floor(span/7))));
  try{fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} timing ${label} die=${die} delay_ms=${delay}\n`);}catch{}
  await wait(delay);
  return {die,delay};
}
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
  const typing=await typeWithVirtualKeyboard(contents,value,'follower-welcome');
  const entered=await contents.executeJavaScript(`(()=>{const e=document.activeElement;return (e?.value||e?.innerText||e?.textContent||'').trim()===${JSON.stringify(value)}})()`,true);
  if(!entered)throw new Error('A mensagem não entrou no campo do Instagram.');
  contents.sendInputEvent({type:'keyDown',keyCode:'ENTER'});
  contents.sendInputEvent({type:'keyUp',keyCode:'ENTER'});
  for(let i=0;i<12;i++){
    await wait(500);
    if(await conversationMessageCount(contents,value)>before)return {sent:true,method:'virtual-keyboard-accessibility-chat-metadata',typing};
  }
  const error=new Error('O Instagram não confirmou a mensagem na área da conversa.');
  error.deliveryAttempted=true;
  throw error;
}
async function sendSingleInBrowserView(text){
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
  view.webContents.sendInputEvent({type:'mouseDown',x:Math.round(target.x),y:Math.round(target.y),button:'left',clickCount:1});
  view.webContents.sendInputEvent({type:'mouseUp',x:Math.round(target.x),y:Math.round(target.y),button:'left',clickCount:1});
  await new Promise(r=>setTimeout(r,120));
  const typing=await typeWithVirtualKeyboard(view.webContents,value,'dm-reply');
  const entered=await view.webContents.executeJavaScript(`(()=>{const e=document.activeElement;return (e?.value||e?.innerText||e?.textContent||'').trim()===${JSON.stringify(value)}})()`,true);
  if(!entered) throw new Error('O texto não foi inserido no campo da mensagem.');
  if(view.webContents.getURL()!==url) throw new Error('A conversa mudou antes do envio.');
  view.webContents.sendInputEvent({type:'keyDown',keyCode:'ENTER'});
  view.webContents.sendInputEvent({type:'keyUp',keyCode:'ENTER'});
  for(let i=0;i<10;i++){
    await new Promise(r=>setTimeout(r,500));
    if(view.webContents.getURL()!==url) throw new Error('A conversa mudou antes da confirmação do envio.');
    if(await countMatches()>before) return {sent:true,method:'mouse-virtual-keyboard-enter',typing};
  }
  // O Instagram nem sempre expõe as bolhas como nós DOM consultáveis. A
  // árvore de acessibilidade continua sendo uma confirmação confiável porque
  // é a mesma representação usada pelo navegador para exibir a conversa.
  const after=await observeBrowser();
  const delivered=after.messages.at(-1);
  if(delivered?.direction==='outgoing'&&delivered.text.trim()===value){
    return {sent:true,method:'mouse-virtual-keyboard-enter-accessibility',typing};
  }
  throw new Error('Não foi possível confirmar a mensagem na conversa.');
}
async function sendInBrowserView(text){
  const bubbles=String(text||'').split(AGENT_BUBBLE_SEPARATOR).map(item=>item.trim()).filter(Boolean);
  if(!bubbles.length)throw new Error('Mensagem vazia.');
  const sent=[];
  for(let index=0;index<bubbles.length;index++){
    sent.push(await sendSingleInBrowserView(bubbles[index]));
    if(index<bubbles.length-1)await naturalInteractionPause('message-bubble',700,2600);
  }
  return bubbles.length===1?sent[0]:{sent:true,method:'virtual-keyboard-bubble-sequence',messages:sent.length,details:sent};
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
  return {open:true,url:view.webContents.getURL()||browserPaneUrl,browser_error:browserLoadError||undefined};
});
ipcMain.handle('sales:remoteMode', async event => {
  if(event.sender!==window.webContents) throw new Error('Origem inválida');
  return isRemoteControl;
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
async function collectInboxThreadTargets(view){
  /*
   * O Instagram alterna entre duas estruturas para a lista de DMs. Em uma
   * delas cada conversa tem um link /direct/t/, na outra (inclusive na tela
   * atual da conta) a conversa é somente um botão acessível. Guardamos uma
   * assinatura de texto e não um índice DOM: ao voltar da conversa o React
   * recria a lista e os índices deixam de ser confiáveis.
   */
  return view.webContents.executeJavaScript(`(()=>{
    const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};
    const normalize=value=>String(value||'').replace(/\\s+/g,' ').trim();
    const time=/(?:agora|now|ontem|yesterday|há\\s+(?:\\d+|um|uma)\\s+(?:minuto|minutos|hora|horas|dia|dias)|\\b\\d+\\s*(?:s|min|m|h|d|w))\\s*$/i;
    const ignored=/^(?:avançar|voltar|nova mensagem|more options|pesquisar|primary|general|pedidos)$/i;
    const result=[];
    for(const node of [...document.querySelectorAll('a[href*="/direct/t/"],button,[role="button"]')]){
      if(!visible(node))continue;
      const label=normalize([node.getAttribute('aria-label'),node.innerText].filter(Boolean).join(' '));
      const href=node.matches('a[href]')?node.href:(node.querySelector('a[href*="/direct/t/"]')?.href||'');
      const looksLikeThread=Boolean(href)||(!ignored.test(label)&&label.length>8&&time.test(label));
      if(!looksLikeThread)continue;
      const key=href||label;
      if(!result.some(item=>item.key===key))result.push({key,label:label.slice(0,360),href});
    }
    return result.slice(0,80);
  })()`,true);
}
async function openInboxThreadTarget(view,target){
  if(target.href){
    await view.webContents.loadURL(target.href);
  }else{
    const clicked=await view.webContents.executeJavaScript(`(()=>{
      const expected=${JSON.stringify(String(target.label||''))};
      const normalize=value=>String(value||'').replace(/\\s+/g,' ').trim();
      const candidates=[...document.querySelectorAll('button,[role="button"]')];
      const node=candidates.find(item=>normalize([item.getAttribute('aria-label'),item.innerText].filter(Boolean).join(' '))===expected);
      if(!node)return false;node.click();return true;
    })()`,true);
    if(!clicked)return false;
  }
  for(let attempt=0;attempt<14;attempt++){
    await wait(450);
    const path=new URL(view.webContents.getURL()||'https://www.instagram.com/').pathname.split('/').filter(Boolean);
    if(path.length===3&&path[0]==='direct'&&path[1]==='t')return true;
  }
  return false;
}
async function processCurrentBrowserThread(view,{source='sweep'}={}){
  const snap=await observeBrowser();
  if(!snap.threadId||!snap.username||!snap.messages.length)return {processed:false,reason:'thread-metadata-unavailable'};
  // A cópia da conversa vem antes da decisão do agente. Assim, mesmo que uma
  // página mude durante o ciclo, o histórico e o estado de atendimento ficam
  // preservados na memória local do lead.
  try{await backend('browserImportThread',{thread_id:snap.threadId,username:snap.username,messages:snap.messages});}catch(error){
    fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} ${source} import-error ${error.message}\n`);
  }
  const last=snap.messages.at(-1);
  if(!last?.id||!last.text||last.direction!=='incoming')return {processed:true,replied:false,reason:'no-pending-incoming',threadId:snap.threadId};
  const cycle=await backend('browserScreenCycle',{url:snap.url,thread_id:snap.threadId,username:snap.username,message_id:last.id,message:last.text,direction:'incoming',messages:snap.messages});
  if(!cycle?.new_message||!cycle.text)return {processed:true,replied:false,reason:'already-handled-or-no-draft',threadId:snap.threadId};
  await naturalInteractionPause('dm-reply',2400,11000);
  const state=await backend('agentStatus');
  if(!state.active||view.webContents.getURL()!==snap.url)return {processed:true,replied:false,reason:'conversation-changed',threadId:snap.threadId};
  if(cycle.competitor?.asset_ready){
    try{await sendImageInBrowserView(cycle.competitor.asset_path);}catch(error){
      fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} ${source} poster-error ${cycle.competitor.slug} ${error.message}\n`);
    }
  }
  const delivery=await sendInBrowserView(cycle.text);
  // Só registramos a conclusão depois que o navegador confirmou a bolha na
  // conversa. Essa chave torna uma nova varredura idempotente.
  await backend('browserScreenConfirm',{message_key:cycle.message_key,lead_id:cycle.lead_id,text:cycle.text,thread_id:snap.threadId});
  fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} ${source} confirmed ${JSON.stringify({threadId:snap.threadId,username:snap.username,messageKey:cycle.message_key,delivery:delivery.method||'confirmed'})}\n`);
  return {processed:true,replied:true,threadId:snap.threadId,username:snap.username};
}
async function runInboxSweep(view,{source='scheduled'}={}){
  const current=view.webContents.getURL()||'';
  if(!current.includes('instagram.com'))throw new Error('Abra o Instagram no navegador interno antes da varredura.');
  await view.webContents.loadURL('https://www.instagram.com/direct/inbox/');
  await wait(1200);
  const targets=await collectInboxThreadTargets(view);
  let opened=0, imported=0, replied=0, skipped=0;
  for(const target of targets){
    try{
      if(!(await openInboxThreadTarget(view,target))){skipped++;continue;}
      opened++;await wait(700);
      const result=await processCurrentBrowserThread(view,{source});
      if(result.processed)imported++;
      if(result.replied)replied++;
    }catch(error){
      skipped++;
      fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} ${source} thread-error ${error.message}\n`);
    }finally{
      if((view.webContents.getURL()||'').includes('instagram.com/direct')){
        await view.webContents.loadURL('https://www.instagram.com/direct/inbox/').catch(()=>null);
        await wait(650);
      }
    }
  }
  const classification=await backend('classifyImportedHistory',{}).catch(()=>({count:0}));
  saveInboxSweepState();
  await view.webContents.loadURL('https://www.instagram.com/');
  return {source,threads:targets.length,opened,imported,replied,skipped,classified:Number(classification.count||0),nextDueAt:lastInboxSweepAt+INBOX_SWEEP_INTERVAL_MS};
}
ipcMain.handle('sales:importBrowserInbox', async (event) => {
  if(event.sender!==window.webContents) throw new Error('Origem inválida');
  const view=ensureBrowserView();
  const current=view.webContents.getURL()||'';
  if(!current.includes('instagram.com')) throw new Error('Entre no Instagram pelo navegador interno antes de importar as DMs.');
  const result=await runInboxSweep(view,{source:'manual'});
  return {...result,messages:result.imported};
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
let browserAutomationArmed=false;
let followerScanRequested=false;
let messageScanRequested=false;
let messageProcessing=false;
let nextMessageScanAt=0;
let lastFollowerScanAt=0;
let nextFollowerScanAt=0;
// A caixa de entrada inteira é uma operação deliberadamente espaçada. Além
// de preservar a sessão do operador na tela de perfil, isto impede que o
// navegador fique entrando e saindo das DMs a cada ciclo do agente.
const INBOX_SWEEP_INTERVAL_MS=7*24*60*60*1000;
const inboxSweepStatePath=()=>path.join(app.getPath('userData'),'instagram-inbox-sweep.json');
let lastInboxSweepAt=0;
function loadInboxSweepState(){
  try{
    const parsed=JSON.parse(fs.readFileSync(inboxSweepStatePath(),'utf8'));
    const value=Number(parsed?.lastCompletedAt||0);
    lastInboxSweepAt=Number.isFinite(value)&&value>0?value:0;
  }catch{lastInboxSweepAt=0;}
}
function saveInboxSweepState(completedAt=Date.now()){
  lastInboxSweepAt=completedAt;
  try{fs.mkdirSync(app.getPath('userData'),{recursive:true});fs.writeFileSync(inboxSweepStatePath(),JSON.stringify({lastCompletedAt:completedAt,nextDueAt:completedAt+INBOX_SWEEP_INTERVAL_MS},null,2));}catch{}
}
loadInboxSweepState();
function inboxSweepDue(now=Date.now()){
  return !lastInboxSweepAt||now-lastInboxSweepAt>=INBOX_SWEEP_INTERVAL_MS;
}
function isSalesProfilePage(url){
  try{
    const parsed=new URL(url);
    if(!/(^|\.)instagram\.com$/i.test(parsed.hostname))return false;
    const profile=parsed.pathname.split('/').filter(Boolean)[0]?.toLowerCase()||'';
    const target=String(process.env.INSTAGRAM_TARGET_USERNAME||'erpclinicatea').replace(/^@/,'').toLowerCase();
    return Boolean(profile)&&profile===target;
  }catch{return false;}
}
async function scanInstagramHome(view,{openInbox=true}={}){
  /* A página inicial mantém contadores no DOM/árvore de acessibilidade. O
     Instagram alterna entre rótulos, ícones SVG e rotas sem texto; por isso a
     leitura usa os três sinais, sem depender de posição ou de imagem. */
  const indicators=await view.webContents.executeJavaScript(`(()=>{
    const nodes=[...document.querySelectorAll('a,button,[role="link"],[role="button"]')];
    const description=node=>((node.innerText||'')+' '+(node.getAttribute('aria-label')||'')+' '+(node.getAttribute('title')||'')+' '+(node.getAttribute('href')||'')).replace(/\\s+/g,' ').trim();
    const route=(node,kind)=>{
      const href=node.getAttribute('href')||'';
      return kind==='notification'
        ? /\\/(?:notifications|accounts\\/activity)\\/?(?:[?#]|$)/i.test(href)
        : /\\/direct(?:\\/inbox)?\\/?(?:[?#]|$)/i.test(href);
    };
    const isRed=color=>{
      const match=String(color||'').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/i);
      return !!match&&Number(match[1])>=180&&Number(match[2])<=165&&Number(match[3])<=165;
    };
    const badgeFor=node=>{
      const text=description(node);
      if(/(?:nova|new|unread|não lida|\\b\\d+\\s*(?:notifica|message|mensage))/i.test(text))return true;
      // Em algumas versões o ponto fica em um irmão do SVG. Considerar o
      // controle, seu conteúdo e um único nível acima torna a leitura estável
      // sem varrer a página inteira e sem reconhecimento visual por pixel.
      const scope=[node,...node.querySelectorAll('*'),...(node.parentElement?[node.parentElement]:[])];
      return scope.some(child=>{
        const rect=child.getBoundingClientRect();
        const style=getComputedStyle(child);
        const label=[child.getAttribute('aria-label'),child.getAttribute('title'),child.textContent].filter(Boolean).join(' ');
        return (/^(?:\\d+|nova|new)$/i.test(label.trim())||isRed(style.backgroundColor)||isRed(style.color))
          &&rect.width>=3&&rect.width<=34&&rect.height>=3&&rect.height<=34;
      });
    };
    const collect=(kind,pattern)=>nodes.filter(node=>route(node,kind)||pattern.test(description(node))).map(node=>({
      text:description(node).slice(0,140),href:node.href||'',badge:badgeFor(node)
    }));
    const notifications=collect('notification',/notifica(?:ç|c)(?:ões|oes)|notifications|activity/i);
    const messages=collect('message',/mensagens|messages|direct/i);
    return {messages,notifications,redBadge:notifications.some(item=>item.badge)};
  })()`,true);
  const hasMessage=indicators.messages.some(item=>item.badge||/nova|new|unread|não lida/i.test(item.text));
  const hasNotification=Boolean(indicators.redBadge)||indicators.notifications.some(item=>item.badge||/nova|new/i.test(item.text));
  // O registro é somente diagnóstico agregado. Nunca inclua URLs integrais
  // do feed/notificações, pois links de redirecionamento podem conter dados
  // efêmeros da sessão.
  fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} home indicators ${JSON.stringify({hasMessage,hasNotification,messageControls:indicators.messages.length,notificationControls:indicators.notifications.length,redBadge:indicators.redBadge})}\n`);
  if(hasMessage&&openInbox){
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
async function isInstagramAuthenticatedArea(view,url){
  if(isInstagramAuthenticationPage(url))return false;
  try{
    return await view.webContents.executeJavaScript(`(()=>{
      const target=${JSON.stringify(String(process.env.INSTAGRAM_TARGET_USERNAME||'erpclinicatea').replace(/^@/,'').toLowerCase())};
      const links=[...document.querySelectorAll('a[href]')];
      const ownProfile=links.some(link=>new URL(link.href,location.href).pathname.replace(/^\\/+|\\/+$/g,'').toLowerCase()===target);
      const controls=[...document.querySelectorAll('a,button,[role="link"],[role="button"]')];
      const labels=controls.map(item=>[item.innerText,item.getAttribute('aria-label'),item.getAttribute('title'),item.getAttribute('href')].filter(Boolean).join(' ')).join(' ').toLowerCase();
      const navigation=/perfil|profile|página inicial|home|mensagens|messages|notificações|notifications/.test(labels);
      const loginPrompt=/\\b(?:entrar|login|log in|sign up|cadastre-se|criar conta)\\b/.test(labels)||links.some(link=>/\\/accounts\\/(?:login|signup)|\\/accounts\\/password/i.test(link.getAttribute('href')||''));
      const hasSessionRoute=links.some(link=>/\\/(?:direct(?:\\/inbox)?|notifications|accounts\\/activity)\\/?(?:[?#]|$)/i.test(link.getAttribute('href')||''));
      const hasCredentialField=[...document.querySelectorAll('input,textarea,[contenteditable="true"]')].some(field=>/username|senha|password|one-time-code|verification|security code|c[oó]digo/i.test([field.name,field.type,field.autocomplete,field.placeholder,field.getAttribute('aria-label')].filter(Boolean).join(' ').toLowerCase()));
      // A navegação autenticada muda frequentemente de estrutura e pode não
      // expor o texto do próprio perfil. As rotas internas (direct/activity),
      // sem campos ou links de login, continuam disponíveis e são a fonte
      // estável para armar a observação logo após a página inicial carregar.
      return !loginPrompt&&!hasCredentialField&&(ownProfile||navigation||hasSessionRoute);
    })()`,true);
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
  if(isRemoteControl)return;
  if(browserProcessing||!window||window.isDestroyed())return;
  browserProcessing=true;
  try{
    fs.mkdirSync(app.getPath('userData'),{recursive:true});
    const activeView=ensureBrowserView();
    const state=await backend('agentStatus');
    let url=activeView.webContents.getURL()||'';
    fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} tick ${JSON.stringify({active:!!state.active,url,armed:browserAutomationArmed})}\n`);
    if(!state.active||!url)return;
    // A sessão é sempre concluída manualmente. O perfil oficial aberto é o
    // único gatilho que libera as rotinas; até então nenhum ciclo muda a tela.
    if(!browserAutomationArmed){
      // Depois da autenticação, tanto o perfil oficial quanto a tela inicial
      // autenticada oferecem metadados suficientes para iniciar a observação.
      // A tela de login/desafio continua totalmente livre de automação.
      if(!isSalesProfilePage(url)&&!(await isInstagramAuthenticatedArea(activeView,url)))return;
      browserAutomationArmed=true;
      fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} automation armed profile ${url}\n`);
    }
    // Nunca interrompa a autenticação manual. Enquanto a página de login,
    // desafio ou checkpoint estiver aberta, o operador controla a tela e o
    // ciclo aguarda o Instagram concluir a sessão por conta própria.
    if(await isInstagramAuthenticationScreen(activeView,url))return;
    // A lista inteira de DMs é aberta uma vez na primeira ativação e depois
    // semanalmente. Fora disso o agente não tira o operador da tela atual.
    if(isSalesProfilePage(url)||await isInstagramAuthenticatedArea(activeView,url)){
      // O indicador da área de notificações é lido sem navegar nem recarregar
      // o perfil. Assim, um novo seguidor dispara a fila própria de
      // seguidores e a tela do operador continua intacta.
      const home=await scanInstagramHome(activeView,{openInbox:false});
      if(home.hasNotification)followerScanRequested=true;
      // Um indicador de DM não lida tem prioridade: abre somente uma
      // conversa por rodada, preserva o contexto e deixa a decisão/deduplicação
      // no ciclo de atendimento. Curtidas nunca entram nesta fila.
      if(home.hasMessage&&Date.now()>=nextMessageScanAt)messageScanRequested=true;
      if(inboxSweepDue()){
        const result=await runInboxSweep(activeView,{source:'scheduled'});
        fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} scheduled sweep ${JSON.stringify(result)}\n`);
      }
      return;
    }
    if(!url.includes('instagram.com/direct'))return;
    if(new URL(url).pathname.startsWith('/direct/inbox')){await openUnreadConversation(activeView);return;}
    const result=await processCurrentBrowserThread(activeView,{source:'open-thread'});
    fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} open-thread ${JSON.stringify(result)}\n`);
  }catch(error){try{fs.mkdirSync(app.getPath('userData'),{recursive:true});fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} error ${error.message}\n`);}catch{}} finally{browserProcessing=false;}
},15000);
browserTimer.unref();
async function processMessageNotification(view){
  await view.webContents.loadURL('https://www.instagram.com/direct/inbox/');
  await wait(1200);
  const opened=await openUnreadConversation(view);
  if(!opened)return {processed:false,reason:'no-pending-thread'};
  await wait(650);
  return processCurrentBrowserThread(view,{source:'message-notification'});
}
const messageTimer=setInterval(async()=>{
  if(isRemoteControl)return;
  if(messageProcessing||browserProcessing||!messageScanRequested||!browserAutomationArmed||!app.isReady()||!window||window.isDestroyed())return;
  messageProcessing=true;
  browserProcessing=true;
  messageScanRequested=false;
  try{
    const state=await backend('agentStatus');
    if(!state.active)return;
    const view=ensureBrowserView();
    const url=view.webContents.getURL()||'';
    if(!url.includes('instagram.com')||await isInstagramAuthenticationScreen(view,url))return;
    const result=await processMessageNotification(view);
    fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} message-notification ${JSON.stringify(result)}\n`);
  }catch(error){
    try{fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} message-notification-error ${error.message}\n`);}catch{}
  }finally{
    // Se o ponto de DM continuar visível, a próxima verificação terá uma
    // pequena pausa. Assim várias mensagens são atendidas em sequência sem
    // prender o navegador em um loop agressivo.
    nextMessageScanAt=Date.now()+30000+crypto.randomInt(0,30001);
    const view=browserView;
    if(view&&!view.webContents.isDestroyed()&&(view.webContents.getURL()||'').includes('instagram.com/direct')){
      await view.webContents.loadURL('https://www.instagram.com/').catch(()=>null);
    }
    browserProcessing=false;
    messageProcessing=false;
  }
},5000);
messageTimer.unref();
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
    // Curtidas, menções e comentários ficam fora deste filtro. Uma atividade
    // só pode gerar uma ação comercial quando descreve explicitamente que a
    // pessoa passou a seguir a conta.
    const isFollowerText=text=>/(?:começou|passou|acabou)(?:\\s+de)? a seguir(?: você)?|(?:segue|seguiu|está seguindo)(?: você)?|started following you|follows you/i.test(text);
    const parts=[...document.querySelectorAll('span,div,p')].filter(e=>{
      const text=(e.innerText||'').replace(/\s+/g,' ').trim();
      return text.length>0&&text.length<320&&isFollowerText(text);
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
    for(const marker of nodes.filter(node=>/(?:começou|passou|acabou)(?:\s+de)? a seguir(?: você)?|(?:segue|seguiu|está seguindo)(?: você)?|started following you|follows you/i.test(String(node.name?.value||'')))){
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
  let state=await contents.executeJavaScript(`(()=>({url:location.href,hasFollowerText:/(?:começou|passou|acabou)(?:\\s+de)? a seguir(?: você)?|(?:segue|seguiu|está seguindo)(?: você)?|started following you|follows you/i.test(document.body?.innerText||'')}))()`,true);
  if(state.hasFollowerText)return {...state,opened:false};
  const opened=await contents.executeJavaScript(`(()=>{
    const elements=[...document.querySelectorAll('a,button,[role="link"],[role="button"],[aria-label]')];
    const exact=elements.find(e=>/^(notificações|notifications)$/i.test((e.getAttribute('aria-label')||e.innerText||'').replace(/\s+/g,' ').trim()));
    const route=elements.find(e=>(e.getAttribute('href')||'').includes('/accounts/activity'));
    const target=exact||route;
    if(!target)return false;(target.closest('a,button,[role="link"],[role="button"]')||target).click();return true;
  })()`,true);
  if(opened)await wait(1800);
  state=await contents.executeJavaScript(`(()=>({url:location.href,hasFollowerText:/(?:começou|passou|acabou)(?:\\s+de)? a seguir(?: você)?|(?:segue|seguiu|está seguindo)(?: você)?|started following you|follows you/i.test(document.body?.innerText||'')}))()`,true);
  return {...state,opened};
}
async function followAndOpenMessage(contents,username,openMessage=true,allowFollow=true){
  const followed=allowFollow&&await contents.executeJavaScript(`(()=>{
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
  const followedOnProfile=allowFollow&&await contents.executeJavaScript(`(()=>{
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
async function engageWithProfilePost(contents,username){
  // Uma rodada positiva usa a própria janela e não repete o mesmo perfil.
  // Controles opcionais ausentes em uma versão da interface não bloqueiam a DM.
  const result={liked:false,commented:false,reshared:false};
  const postOpened=await contents.executeJavaScript(`(()=>{
    const link=[...document.querySelectorAll('a[href]')].find(a=>{try{return /\/(?:p|reel)\/[A-Za-z0-9_-]+/.test(new URL(a.href,location.href).pathname)}catch{return false}});
    if(!link)return false;(link.closest('a')||link).click();return true;
  })()`,true);
  if(postOpened)await wait(1800);
  result.liked=Boolean(await contents.executeJavaScript(`(()=>{
    const buttons=[...document.querySelectorAll('button,[role="button"],[aria-label]')];
    const button=buttons.find(e=>/^(?:curtir|like)$/i.test((e.getAttribute('aria-label')||e.innerText||'').trim())&&!/(?:descurtir|unlike)/i.test((e.getAttribute('aria-label')||e.innerText||'')));
    if(!button)return false;(button.closest('button,[role="button"]')||button).click();return true;
  })()`,true));
  if(result.liked)await naturalInteractionPause('campaign-like',900,2600);
  const commentReady=await contents.executeJavaScript(`(()=>{
    const fields=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')];
    const field=fields.find(e=>/coment[aá]rio|comment|adicionar/i.test((e.getAttribute('placeholder')||'')+' '+(e.getAttribute('aria-label')||'')));
    if(!field)return false;field.focus();return document.activeElement===field;
  })()`,true);
  if(commentReady){
    await typeWithVirtualKeyboard(contents,'Muito bonito o trabalho de vocês! 😊','campaign-comment');
    contents.sendInputEvent({type:'keyDown',keyCode:'ENTER'});contents.sendInputEvent({type:'keyUp',keyCode:'ENTER'});
    result.commented=true;await naturalInteractionPause('campaign-comment',1200,3200);
  }
  const shareClicked=await contents.executeJavaScript(`(()=>{
    const buttons=[...document.querySelectorAll('button,[role="button"],[aria-label]')];
    const button=buttons.find(e=>/^(?:compartilhar|share|repost|recompartilhar)$/i.test((e.getAttribute('aria-label')||e.innerText||'').trim()));
    if(!button)return false;(button.closest('button,[role="button"]')||button).click();return true;
  })()`,true);
  if(shareClicked){
    await wait(700);
    const reposted=await contents.executeJavaScript(`(()=>{
      const items=[...document.querySelectorAll('button,[role="button"],a')];
      const item=items.find(e=>/^(?:repost|recompartilhar|compartilhar no feed|share to feed)$/i.test((e.innerText||e.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim()));
      if(!item)return false;(item.closest('button,[role="button"],a')||item).click();return true;
    })()`,true);
    result.reshared=Boolean(reposted);
    if(result.reshared)await naturalInteractionPause('campaign-reshare',1000,2800);
  }
  try{fs.appendFileSync(path.join(app.getPath('userData'),'browser-send.log'),`${new Date().toISOString()} campaign-engagement @${username} ${JSON.stringify(result)}\n`);}catch{}
  return result;
}
let followerProcessing=false;
const followerTimer=setInterval(async()=>{
  if(isRemoteControl)return;
  if(followerProcessing||!browserAutomationArmed||!app.isReady()||!window||window.isDestroyed())return;
  const now=Date.now();
  // Consulta de atualizações com ritmo humano: uma rodada inicial ao armar o
  // perfil e, depois, somente após cinco minutos ou mais.
  if(now<nextFollowerScanAt&&!followerScanRequested)return;
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
    // Primeiro lê o perfil sem segui-lo. Só um perfil classificado como
    // compatível e liberado pela roleta de ritmo pode disparar uma interação.
    const inspection=await followAndOpenMessage(contents,candidate.username,false,false);
    const pacing=await backend('prospectingPacing',{mode:'status'});
    if(!pacing.ready){
      followerLog(`paced @${candidate.username} wait_seconds=${pacing.wait_seconds}`);
      return;
    }
    const cycle=await backend('followerCycle',{username:candidate.username,profile:inspection.profile});
    if(!cycle?.new_follower)return;
    claimedUsername=candidate.username;
    followerLog(`detected @${claimedUsername}`);
    const reserved=await backend('prospectingPacing',{mode:'reserve',kind:'instagram_new_follower',target:claimedUsername});
    if(!reserved.reserved){
      await backend('followerReset',{username:claimedUsername});
      followerLog(`reservation-lost @${claimedUsername} wait_seconds=${reserved.wait_seconds||0}`);
      return;
    }
    followerLog(`round @${claimedUsername} die=${reserved.roll} interval_seconds=${reserved.interval_seconds}`);
    await followAndOpenMessage(contents,claimedUsername,true);
    if(await conversationMessageCount(contents,cycle.text)>0){
      await backend('followerConfirm',{username:claimedUsername,text:cycle.text});
      followerLog(`confirmed-existing @${claimedUsername}`);
      return;
    }
    await naturalInteractionPause('new-follower-message');
    if(!(await backend('agentStatus')).active)throw new Error('Agente desativado antes da mensagem.');
    const sent=await sendTextInFollowerWindow(cycle.text);
    await backend('followerConfirm',{username:claimedUsername,text:cycle.text});
    followerLog(`completed @${claimedUsername} ${JSON.stringify(sent)}`);
  }catch(error){
    followerLog(`error ${claimedUsername?'@'+claimedUsername+' ':''}${error.message}`);
    if(claimedUsername&&error.deliveryAttempted){
      followerLog(`pending-confirmation @${claimedUsername}; envio bloqueado para evitar duplicação`);
    }else if(claimedUsername)await backend('followerReset',{username:claimedUsername}).catch(()=>null);
  }finally{
    lastFollowerScanAt=Date.now();
    const die=interactionDie();
    const interval=300000+(die*30000)+crypto.randomInt(5000,45001);
    nextFollowerScanAt=lastFollowerScanAt+interval;
    followerLog(`next-scan die=${die} interval_seconds=${Math.round(interval/1000)}`);
    followerProcessing=false;
  }
},8000);
followerTimer.unref();
// A prospecção ativa usa a mesma roleta persistente do CRM. Uma rodada pega
// somente uma campanha por vez, confere o perfil e confirma o envio apenas
// depois que a mensagem aparece na própria conversa do Instagram.
let campaignProcessing=false;
const campaignTimer=setInterval(async()=>{
  if(isRemoteControl)return;
  if(campaignProcessing||!browserAutomationArmed||!app.isReady()||!window||window.isDestroyed())return;
  campaignProcessing=true;
  let campaignId=0;
  try{
    const state=await backend('agentStatus');
    if(!state.active||!state.prospecting_active)return;
    const pacing=await backend('prospectingPacing',{mode:'status'});
    if(!pacing.ready)return;
    const claim=await backend('campaignClaim',{});
    if(!claim?.claimed)return;
    campaignId=Number(claim.id);
    const payload=claim.payload||{};
    const username=String(payload.username||'').replace(/^@/,'').toLowerCase();
    const intro=String(payload.intro||'Olá! Muito legal o trabalho de vocês ❤️').trim();
    if(!/^[a-z0-9._]{1,30}$/.test(username)||!intro)throw new Error('Dados de campanha inválidos.');
    const reserved=await backend('prospectingPacing',{mode:'reserve',kind:'instagram_campaign',target:username});
    if(!reserved.reserved){
      await backend('campaignConfirm',{id:campaignId,state:'pending',note:'Aguardando a próxima janela da roleta'});
      return;
    }
    const contents=ensureFollowerWindow().webContents;
    // Inspeção antes da interação evita seguir perfis cuja tela não possa ser
    // lida no momento; não executa ação externa nesta primeira passagem.
    await followAndOpenMessage(contents,username,false,false);
    await engageWithProfilePost(contents,username);
    await followAndOpenMessage(contents,username,true,true);
    await naturalInteractionPause('campaign-intro',2200,8500);
    const sent=await sendTextInFollowerWindow(intro);
    await backend('campaignConfirm',{id:campaignId,state:'sent',note:`DM confirmada por metadados (${sent.method||'browser'})`});
    followerLog(`campaign @${username} die=${reserved.roll} interval_seconds=${reserved.interval_seconds}`);
  }catch(error){
    if(campaignId){
      const state=error?.deliveryAttempted?'needs_check':'pending';
      await backend('campaignConfirm',{id:campaignId,state,note:String(error?.message||error).slice(0,900)}).catch(()=>null);
    }
    followerLog(`campaign-error ${error?.message||error}`);
  }finally{campaignProcessing=false;}
},15000);
campaignTimer.unref();
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
    if(sessionExportPath){
      try{await exportPersistentBrowserSession(sessionExportPath);app.quit();return;}catch(error){record(error);app.quit();return;}
    }
    startMetaCallbackServer();
    // A edição de controle remoto precisa manter seu próprio túnel durante
    // toda a vida do aplicativo. Não espere o primeiro clique/consulta para
    // abrir a conexão, pois isso deixava o painel em estado parcial após um
    // reinício da aplicação.
    if(remoteControl) startRemoteTunnel();
    // O supervisor sobe os serviços locais em paralelo. A janela não deve
    // esperar tentativas de conexão com Ollama/BrowserOS para ficar utilizável.
    backend('startServices').catch(()=>null);
    window = new BrowserWindow({width:1660,height:980,minWidth:1000,minHeight:700,title:'Agente de Vendas Local',icon:path.join(__dirname,'..','frontend','icon.svg'),backgroundColor:'#07111f',autoHideMenuBar:true,show:true,webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true}});
    window.webContents.setWindowOpenHandler(() => ({action:'deny'}));
    window.webContents.on('will-navigate', (event, url) => {if(!url.startsWith('file:')) event.preventDefault();});
    window.once('ready-to-show', () => window.show());
    window.on('resize',()=>{if(browserAttached&&browserView&&!browserView.webContents.isDestroyed())browserView.setBounds(browserBounds());});
    await window.loadFile(path.join(__dirname,'..','frontend','index.html'));
    // O navegador interno é a ferramenta principal do agente: já abre
    // exposto no Instagram para o operador iniciar ou acompanhar interações.
    if(!isRemoteControl){
      const initialBrowser=ensureBrowserView();
      browserUserVisible=true;
      window.setBrowserView(initialBrowser);
      browserAttached=true;
      initialBrowser.setBounds(browserBounds());
      initialBrowser.setAutoResize({width:true,height:true});
      if(!initialBrowser.webContents.getURL()) await initialBrowser.webContents.loadURL(browserPaneUrl).catch(error=>{
        browserLoadError=String(error?.message||error).slice(0,180);
        try{fs.appendFileSync(path.join(app.getPath('userData'),'desktop.log'),`${new Date().toISOString()} browser-start ${browserLoadError}\n`);}catch{}
      });
    }
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
