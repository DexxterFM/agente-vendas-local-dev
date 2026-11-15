const {packager}=require('@electron/packager');
const path=require('node:path');
const fs=require('node:fs/promises');
const root=path.join(__dirname,'..');
const out=path.join(root,'dist','remote-control');
const allowed=new Set(['package.json','frontend','desktop']);
packager({dir:root,name:'AgenteVendasControleVPS',platform:'win32',arch:'x64',out,overwrite:true,ignore:p=>{const first=p.replace(/^[/\\]/,'').split(/[/\\]/)[0];return Boolean(first)&&!allowed.has(first);}}).then(async output=>{await fs.copyFile(path.join(root,'desktop','remote-control.json'),path.join(output[0],'resources','remote-control.json'));console.log(output[0]);}).catch(error=>{console.error(error);process.exit(1);});
