const {packager}=require('@electron/packager');
const path=require('node:path');
const fs=require('node:fs/promises');
const root=path.join(__dirname,'..');
const out=path.join(root,'dist','desktop-next');
const allowed=new Set(['package.json','frontend','desktop']);
packager({
  dir:root,name:'AgenteVendasLocalAtualizado',platform:'win32',arch:'x64',out,overwrite:true,
  extraResource:['dist/SalesAgentBackend.exe'],
  ignore:p=>{const first=p.replace(/^[/\\]/,'').split(/[/\\]/)[0];return Boolean(first)&&!allowed.has(first);},
}).then(async output=>{
  await fs.cp(path.join(root,'native'),path.join(output[0],'resources','native'),{recursive:true,force:true});
  console.log(output[0]);
}).catch(error=>{console.error(error);process.exit(1);});
