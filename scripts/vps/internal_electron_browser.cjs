/* Navegador persistente da VPS usando o mesmo runtime Electron do aplicativo
 * desktop. A tela é exibida pelo painel remoto via DevTools, mas o site roda
 * em uma janela real com partição persistente — não em uma simulação HTML. */
const {app,BrowserWindow}=require('electron');

const startUrl=process.env.SALES_AGENT_BROWSER_START_URL||'https://www.instagram.com/';
const width=Number(process.env.SALES_AGENT_BROWSER_WIDTH||1280);
const height=Number(process.env.SALES_AGENT_BROWSER_HEIGHT||900);
const allowedHost=host=>['instagram.com','www.instagram.com','facebook.com','www.facebook.com'].includes(host);
const webPreferences={contextIsolation:true,sandbox:true,partition:'persist:sales-agent-browser'};
const windows=new Set();

function allow(url){try{const parsed=new URL(url);return parsed.protocol==='https:'&&allowedHost(parsed.hostname)}catch{return false}}
function createWindow(){
  const win=new BrowserWindow({width,height,show:true,autoHideMenuBar:true,backgroundColor:'#07111f',webPreferences});
  windows.add(win);
  win.on('closed',()=>windows.delete(win));
  win.webContents.setWindowOpenHandler(({url})=>{
    if(!allow(url))return {action:'deny'};
    const child=createWindow();
    child.loadURL(url).catch(()=>{});
    return {action:'deny'};
  });
  win.webContents.on('will-navigate',(event,url)=>{if(!allow(url))event.preventDefault();});
  return win;
}

app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-dev-shm-usage');
app.commandLine.appendSwitch('no-first-run');
app.commandLine.appendSwitch('no-default-browser-check');

app.whenReady().then(()=>{
  const main=createWindow();
  main.loadURL(startUrl).catch(()=>{});
  app.on('activate',()=>{if(!windows.size){const next=createWindow();next.loadURL(startUrl).catch(()=>{});}});
});
app.on('window-all-closed',()=>{});
