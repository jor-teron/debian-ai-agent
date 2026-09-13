"""
Browser chat page (dark UI, sticky confirm, Enter=send).

This module holds the single HTML/CSS/JS page the user sees in the browser.
The page talks to the JSON APIs on server.py (/api/chat, /api/health, …).

Imports from: nothing (string constant only).
Used by: server.py (GET / and /index.html serve HTML).
"""

# ---------------------------------------------------------------------------
# Page markup
# ---------------------------------------------------------------------------

# Full chat page: header (status, provider, model), message log, sticky confirm dock,
# and the composer. Dark by default (color-scheme). Enter sends; Shift+Enter
# is a new line. Confirm/Cancel appear when a shell command is pending.
HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="color-scheme" content="dark"/>
<meta name="theme-color" content="#0f1419"/>
<title>AI Agent</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{font-family:system-ui,sans-serif;background:#0f1419;color:#e7ecf3;display:flex;flex-direction:column;height:100vh;overflow:hidden}
header{flex:0 0 auto;padding:12px 16px;background:#1a2332;display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;border-bottom:1px solid #2a3548}
h1{font-size:1.05rem;margin:0}
.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.field{display:flex;gap:6px;align-items:center}
label{font-size:.8rem;color:#9aa8bc;white-space:nowrap}
select,button,textarea,input[type=file]{font:inherit;border-radius:8px;border:1px solid #2a3548;background:#0c1118;color:#e7ecf3}
select{padding:6px 8px}
#status{font-size:.8rem;color:#9aa8bc;max-width:360px;margin-right:4px}
#status.ok{color:#6ee7b7}#status.bad{color:#f87171}
#note{flex:0 0 auto;font-size:.75rem;color:#fbbf24;padding:0 16px;min-height:0}
#log{flex:1 1 auto;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:10px;min-height:0}
.msg{max-width:820px;padding:10px 12px;border-radius:12px;white-space:pre-wrap;line-height:1.4}
.user{align-self:flex-end;background:#243247}
.bot{align-self:flex-start;background:#1a2332;border:1px solid #2a3548}
.tools{margin-top:6px;font-size:.75rem;color:#9aa8bc}
.dl{margin-top:6px;font-size:.8rem}
.dl a{color:#60a5fa}
#dock{flex:0 0 auto;background:#1a2332;border-top:1px solid #2a3548}
#confirm{display:none;padding:10px 16px;background:#3a2a12;border-bottom:1px solid #5a4020;gap:8px;flex-wrap:wrap;align-items:center}
#confirm.show{display:flex}
#confirm .label{font-size:.85rem;color:#fbbf24;font-weight:600}
#confirm code{flex:1;min-width:120px;word-break:break-all;font-size:.85rem;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#fde68a;background:#1a1208;padding:6px 8px;border-radius:6px}
#confirm .ok{background:#6ee7b7;color:#041018}#confirm .no{background:#f87171;color:#041018}
form{display:flex;gap:8px;padding:12px;flex-wrap:wrap;align-items:end}
textarea{flex:1;min-height:44px;padding:8px;min-width:160px;resize:vertical;max-height:160px}
button{padding:10px 14px;background:#60a5fa;border:none;color:#041018;font-weight:600;cursor:pointer}
button:disabled{opacity:.5}
.up{font-size:.75rem}
</style></head><body>
<header>
  <h1>AI Agent</h1>
  <div class="controls">
    <div id="status">…</div>
    <div class="field"><label for="provider">Provider</label>
      <select id="provider"></select>
    </div>
    <div class="field"><label for="model">Model</label>
      <select id="model"></select>
    </div>
  </div>
</header>
<div id="note"></div>
<div id="log"></div>
<div id="dock">
  <div id="confirm">
    <span class="label">Run shell?</span>
    <code id="pendingCmd"></code>
    <button type="button" class="ok" id="btnConfirm">Confirm</button>
    <button type="button" class="no" id="btnCancel">Cancel</button>
  </div>
  <form id="f">
    <textarea id="input" placeholder="Ask something…" required></textarea>
    <div class="up"><label>Upload</label><input type="file" id="file"/></div>
    <button id="send">Send</button>
  </form>
</div>
<script>
const log=document.getElementById('log'),provider=document.getElementById('provider');
const model=document.getElementById('model');
const status=document.getElementById('status'),input=document.getElementById('input'),send=document.getElementById('send');
const note=document.getElementById('note'),confirmBar=document.getElementById('confirm'),pendingCmd=document.getElementById('pendingCmd');
const fileInput=document.getElementById('file');
let catalog={providers:{},default_provider:'gemini',default_model:'gemini-3.5-flash'}, history=[], keys={};
function fillProviders(){
  provider.innerHTML='';
  Object.keys(catalog.providers||{}).forEach(pid=>{
    const o=document.createElement('option'); o.value=pid;
    const meta=catalog.providers[pid]||{};
    o.textContent=meta.label||pid;
    provider.appendChild(o);
  });
  const sp=localStorage.getItem('p');
  if(sp && catalog.providers[sp]) provider.value=sp;
  else if(catalog.default_provider && catalog.providers[catalog.default_provider]) provider.value=catalog.default_provider;
}
function fillModels(){
  const p=catalog.providers[provider.value]||{models:[]};
  const list=p.models||[];
  model.innerHTML='';
  list.forEach(m=>{const o=document.createElement('option');o.value=m;o.textContent=m;model.appendChild(o);});
  const key='m:'+provider.value;
  const s=localStorage.getItem(key);
  const def=catalog.default_model;
  if(s&&list.includes(s)) model.value=s;
  else if(provider.value===catalog.default_provider && list.includes(def)) model.value=def;
  else if(list[0]) model.value=list[0];
}
function updateStatus(){
  const pid=provider.value;
  const has=!!keys[pid];
  const label=(catalog.providers[pid]&&catalog.providers[pid].label)||pid;
  const ver=window._ver||'?';
  if(has){
    status.textContent='Ready · '+label+' · v'+ver;
    status.className='ok';
  }else{
    status.textContent='No key for '+label+' · v'+ver;
    status.className='bad';
  }
}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function add(role,text,tools){const d=document.createElement('div'); d.className='msg '+(role==='user'?'user':'bot'); d.textContent=text;
  if(tools&&tools.length){const x=document.createElement('details'); x.className='tools'; x.innerHTML='<summary>'+tools.length+' tool(s)</summary><pre>'+esc(JSON.stringify(tools,null,2))+'</pre>'; d.appendChild(x);
    const names=[]; tools.forEach(t=>{const r=t.result||{}; const n=r.name||(r.path&&String(r.path).split('/').pop()); if(n&&(t.name==='write_file'||r.path)) names.push(n);});
    if(names.length){const dl=document.createElement('div'); dl.className='dl'; dl.innerHTML=names.map(n=>'<a href="/api/download?name='+encodeURIComponent(n)+'" download>'+esc(n)+'</a>').join(' · '); d.appendChild(dl);}
  }
  if(role!=='user' && text && text.indexOf('[[download:')>=0){
    const dl=document.createElement('div'); dl.className='dl';
    const re=/\[\[download:([^\]]+)\]\]/g; let m; const seen={};
    while((m=re.exec(text))){const n=m[1].trim(); if(n&&!seen[n]){seen[n]=1; dl.innerHTML+=(dl.innerHTML?' · ':'')+'<a href="/api/download?name='+encodeURIComponent(n)+'" download>'+esc(n)+'</a>';}}
    if(dl.innerHTML) d.appendChild(dl);
  }
  log.appendChild(d); log.scrollTop=log.scrollHeight;}
async function refreshPending(){
  try{
    const p=await fetch('/api/pending').then(r=>r.json());
    if(p.command){pendingCmd.textContent=p.command; confirmBar.classList.add('show');}
    else confirmBar.classList.remove('show');
  }catch(e){}
}
async function boot(){
  try{
    const h=await fetch('/api/health').then(r=>r.json());
    keys=h.keys||{};
    window._ws=h.workspace||'';
    window._ver=h.version||'?';
    if(h.due_reminders&&h.due_reminders.length){
      note.textContent='Due reminders: '+h.due_reminders.map(r=>r.text).join('; ');
    } else note.textContent='';
    const m=await fetch('/api/models').then(r=>r.json());
    catalog={providers:m.providers||{},default_provider:m.default_provider||'gemini',default_model:m.default_model||''};
    fillProviders();
    fillModels();
    updateStatus();
    await refreshPending();
  }catch(e){status.textContent='Cannot reach server'; status.className='bad';}
}
provider.onchange=()=>{localStorage.setItem('p',provider.value); fillModels(); updateStatus();};
model.onchange=()=>localStorage.setItem('m:'+provider.value,model.value);
document.getElementById('btnConfirm').onclick=async()=>{
  const res=await fetch('/api/confirm',{method:'POST'}).then(r=>r.json());
  add('bot', res.ok?('Done.'+((res.stdout||res.stderr)?('\n'+(res.stdout||'')+(res.stderr?('\n'+res.stderr):'')):'')):(res.error||'Confirm failed'));
  refreshPending();
};
document.getElementById('btnCancel').onclick=async()=>{
  await fetch('/api/cancel',{method:'POST'});
  add('bot','Shell cancelled.');
  refreshPending();
};
fileInput.onchange=async()=>{
  const f=fileInput.files&&fileInput.files[0]; if(!f) return;
  send.disabled=true;
  try{
    const buf=await f.arrayBuffer();
    const bytes=new Uint8Array(buf);
    let b64=''; const chunk=0x8000;
    for(let i=0;i<bytes.length;i+=chunk){b64+=String.fromCharCode.apply(null,bytes.subarray(i,i+chunk));}
    b64=btoa(b64);
    const isText=/\.(txt|md|py|sh|json|csv|html|css|js|env|log|yml|yaml)$/i.test(f.name)&&f.size<200000;
    let body;
    if(isText){
      const text=await f.text();
      body={name:f.name,content:text};
    }else{
      body={name:f.name,content:b64,encoding:'base64'};
    }
    const res=await fetch('/api/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json());
    if(res.ok) add('bot','Uploaded '+f.name+' → download: /api/download?name='+encodeURIComponent(f.name)+'  ([[download:'+f.name+']])');
    else add('bot','Upload failed: '+(res.error||'?'));
  }catch(e){add('bot','Upload error: '+e);} finally{fileInput.value=''; send.disabled=false;}
};
input.addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();document.getElementById('f').requestSubmit();}
});
document.getElementById('f').onsubmit=async ev=>{
  ev.preventDefault(); const message=input.value.trim(); if(!message) return;
  add('user',message); input.value=''; send.disabled=true;
  try{
    const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message,provider:provider.value,model:model.value,history})});
    const data=await res.json();
    if(!data.ok) add('bot', data.error||'Failed', data.tools); else {
      add('bot', data.reply, data.tools);
      history.push({role:'user',content:message},{role:'assistant',content:data.reply});
      if(history.length>20) history=history.slice(-20);
    }
    await refreshPending();
    const h=await fetch('/api/health').then(r=>r.json());
    keys=h.keys||keys;
    updateStatus();
    if(h.due_reminders&&h.due_reminders.length) note.textContent='Due reminders: '+h.due_reminders.map(r=>r.text).join('; ');
  }catch(e){add('bot','Network error: '+e);} finally{send.disabled=false; input.focus();}
};
boot();
setInterval(refreshPending, 4000);
setInterval(async()=>{try{const h=await fetch('/api/health').then(r=>r.json());
  keys=h.keys||keys; updateStatus();
  if(h.due_reminders&&h.due_reminders.length) note.textContent='Due reminders: '+h.due_reminders.map(r=>r.text).join('; ');
  else if(note.textContent.startsWith('Due reminders:')) note.textContent='';
}catch(e){}}, 15000);
</script></body></html>
"""
