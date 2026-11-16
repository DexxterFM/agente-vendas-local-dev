import json
from scripts.vps import internal_browser as b
b.DEBUG_URL='http://127.0.0.1:9335'
p=b._http('/json/list')[0]
w=b.DevTools(p['webSocketDebuggerUrl'])
try:
 print(json.dumps(w.call('Runtime.evaluate',{'expression':'''JSON.stringify({layout:(()=>{const e=document.querySelector('#vps-browser-layout');return e?{grid:getComputedStyle(e).gridTemplateColumns,width:e.clientWidth}:null})(),input:(()=>{const e=document.querySelector('#vps-browser-input');return e?{hidden:e.hidden,width:e.clientWidth}:null})(),status:document.querySelector('#vps-browser-status')?.textContent,version:typeof vpsInternalBrowserView==='function'?vpsInternalBrowserView.toString().includes('accessWindowOpen'):null})''','returnByValue':True}),ensure_ascii=False))
finally:w.close()
