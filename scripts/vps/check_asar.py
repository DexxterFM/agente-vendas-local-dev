import subprocess
result = subprocess.run(
    ["node", "-e", "const asar=require('@electron/asar'); const content=asar.extractFile('C:\\\\Users\\\\denis\\\\Documents\\\\opencode\\\\sales_agent_unified\\\\dist\\\\app.asar','/frontend/runtime.js'); console.log('has selectLead:', content.includes('selectLead')); console.log('has messages call:', content.includes(\"call('messages'\")); console.log('size:', content.length);"],
    capture_output=True, text=True
)
print(result.stdout)
print(result.stderr)
