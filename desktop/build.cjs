const {packager}=require('@electron/packager');
const path=require('node:path');
const allowed=new Set(['package.json','frontend','desktop']);
packager({dir:path.join(__dirname,'..'),name:'AgenteVendasLocal',platform:'win32',arch:'x64',out:'dist/desktop',overwrite:true,extraResource:['dist/SalesAgentBackend.exe'],ignore:p=>{const first=p.replace(/^[/\\]/,'').split(/[/\\]/)[0];return Boolean(first)&&!allowed.has(first);}}).then(console.log).catch(e=>{console.error(e);process.exit(1);});
