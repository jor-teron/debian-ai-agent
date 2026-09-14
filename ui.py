"""
Browser chat page (light default, dark available; sticky confirm; Enter=send).

This module holds the single HTML/CSS/JS page the user sees in the browser.
The page talks to the JSON APIs on server.py (/api/chat, /api/health, …).

Imports from: nothing (string constant only).
Used by: server.py (GET / and /index.html serve HTML).
"""

# ---------------------------------------------------------------------------
# Page markup
# ---------------------------------------------------------------------------

# Full chat page: header (status, provider, model, update, theme), message log,
# sticky confirm dock (optional sudo password), and the composer.
# Light is the default theme (localStorage theme=light|dark). Enter sends;
# Shift+Enter is a new line. Confirm/Cancel appear when a shell command is pending.
HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="color-scheme" content="light dark"/>
<meta name="theme-color" content="#f4f6fa"/>
<title>AI Agent</title>
<style>
/* ---- Light (default) ---- */
:root, [data-theme="light"]{
  color-scheme:light;
  --bg:#f4f6fa; --panel:#ffffff; --border:#d8dee9; --text:#1a2332;
  --muted:#5b6b7c; --user:#e8eef8; --bot:#ffffff; --bot-border:#d8dee9;
  --accent:#2563eb; --accent-fg:#ffffff; --ok:#059669; --bad:#dc2626;
  --warn:#b45309; --confirm-bg:#fff7ed; --confirm-border:#fdba74;
  --confirm-code-bg:#fffbeb; --confirm-code:#92400e; --input-bg:#ffffff;
}
/* ---- Dark ---- */
[data-theme="dark"]{
  color-scheme:dark;
  --bg:#0f1419; --panel:#1a2332; --border:#2a3548; --text:#e7ecf3;
  --muted:#9aa8bc; --user:#243247; --bot:#1a2332; --bot-border:#2a3548;
  --accent:#60a5fa; --accent-fg:#041018; --ok:#6ee7b7; --bad:#f87171;
  --warn:#fbbf24; --confirm-bg:#3a2a12; --confirm-border:#5a4020;
  --confirm-code-bg:#1a1208; --confirm-code:#fde68a; --input-bg:#0c1118;
}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);display:flex;flex-direction:column;height:100vh;overflow:hidden}
header{flex:0 0 auto;padding:12px 16px;background:var(--panel);display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border)}
h1{font-size:1.05rem;margin:0;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
h1 .ver{font-size:.75rem;font-weight:500;color:var(--muted)}
#themeBtn{padding:4px 8px;font-size:.85rem;background:transparent;color:var(--muted);border:1px solid var(--border);border-radius:8px;cursor:pointer;line-height:1}
#themeBtn:hover{color:var(--text)}
.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.field{display:flex;gap:6px;align-items:center}
label{font-size:.8rem;color:var(--muted);white-space:nowrap}
select,button,textarea,input[type=file],input[type=password]{font:inherit;border-radius:8px;border:1px solid var(--border);background:var(--input-bg);color:var(--text)}
select{padding:6px 8px}
#btnUpdate{padding:6px 10px;font-size:.8rem;background:var(--panel);color:var(--text);border:1px solid var(--border);font-weight:600;cursor:pointer}
#btnUpdate:hover{border-color:var(--accent)}
#status{font-size:.8rem;color:var(--muted);max-width:360px;margin-right:4px}
#status.ok{color:var(--ok)}#status.bad{color:var(--bad)}
#note{flex:0 0 auto;font-size:.75rem;color:var(--warn);padding:0 16px;min-height:0}
#log{flex:1 1 auto;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:10px;min-height:0}
.msg{max-width:820px;padding:10px 12px;border-radius:12px;white-space:pre-wrap;line-height:1.4}
.user{align-self:flex-end;background:var(--user)}
.bot{align-self:flex-start;background:var(--bot);border:1px solid var(--bot-border)}
.tools{margin-top:6px;font-size:.75rem;color:var(--muted)}
.dl{margin-top:6px;font-size:.8rem}
.dl a{color:var(--accent)}
#dock{flex:0 0 auto;background:var(--panel);border-top:1px solid var(--border)}
#confirm{display:none;padding:10px 16px;background:var(--confirm-bg);border-bottom:1px solid var(--confirm-border);gap:8px;flex-wrap:wrap;align-items:center}
#confirm.show{display:flex}
#confirm .label{font-size:.85rem;color:var(--warn);font-weight:600}
#confirm code{flex:1;min-width:120px;word-break:break-all;font-size:.85rem;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--confirm-code);background:var(--confirm-code-bg);padding:6px 8px;border-radius:6px}
#sudoPassWrap{display:none;align-items:center;gap:6px}
#sudoPassWrap.show{display:flex}
#sudoPass{padding:6px 8px;min-width:140px}
#confirm .ok{background:var(--ok);color:#041018}#confirm .no{background:var(--bad);color:#041018}
form{display:flex;gap:8px;padding:12px;flex-wrap:wrap;align-items:end}
textarea{flex:1;min-height:44px;padding:8px;min-width:160px;resize:vertical;max-height:160px}
button{padding:10px 14px;background:var(--accent);border:none;color:var(--accent-fg);font-weight:600;cursor:pointer}
button:disabled{opacity:.5}
.up{font-size:.75rem}
</style></head><body>
<header>
  <h1>AI Agent <span class="ver" id="ver">…</span>
    <button type="button" id="themeBtn" title="Toggle light/dark theme" aria-label="Toggle theme">◐</button>
  </h1>
  <div class="controls">
    <div id="status">…</div>
    <div class="field"><label for="provider">Provider</label>
      <select id="provider"></select>
    </div>
    <div class="field"><label for="model">Model</label>
      <select id="model"></select>
    </div>
    <button type="button" id="btnUpdate" title="git pull and restart service">Update</button>
  </div>
</header>
<div id="note"></div>
<div id="log"></div>
<div id="dock">
  <div id="confirm">
    <span class="label">Run shell?</span>
    <code id="pendingCmd"></code>
    <span id="sudoPassWrap"><label for="sudoPass">sudo</label>
      <input type="password" id="sudoPass" placeholder="password" autocomplete="current-password"/>
    </span>
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
const sudoPassWrap=document.getElementById('sudoPassWrap'),sudoPass=document.getElementById('sudoPass');
const themeBtn=document.getElementById('themeBtn');
let catalog={providers:{},default_provider:'gemini',default_model:'gemini-3.5-flash-lite'}, history=[], keys={};
let pendingIsSudo=false;

function applyTheme(t){
  const theme=(t==='dark')?'dark':'light';
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);
  const meta=document.querySelector('meta[name="theme-color"]');
  if(meta) meta.content=(theme==='dark')?'#0f1419':'#f4f6fa';
  themeBtn.textContent=(theme==='dark')?'☀':'☾';
  themeBtn.title=(theme==='dark')?'Switch to light':'Switch to dark';
}
(function initTheme(){
  const saved=localStorage.getItem('theme');
  applyTheme(saved==='dark'?'dark':'light'); // light DEFAULT
})();
themeBtn.onclick=()=>{
  const cur=document.documentElement.getAttribute('data-theme')||'light';
  applyTheme(cur==='dark'?'light':'dark');
};

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
  const verEl=document.getElementById('ver');
  if(verEl) verEl.textContent='v'+(window._ver||'?');
  if(has){
    status.textContent='Ready · '+label;
    status.className='ok';
  }else{
    status.textContent='No key for '+label;
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
    if(p.command){
      pendingCmd.textContent=p.command;
      pendingIsSudo=!!p.sudo;
      confirmBar.classList.add('show');
      if(pendingIsSudo){sudoPassWrap.classList.add('show');}
      else{sudoPassWrap.classList.remove('show'); sudoPass.value='';}
    }else{
      confirmBar.classList.remove('show');
      sudoPassWrap.classList.remove('show');
      sudoPass.value='';
      pendingIsSudo=false;
    }
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

document.getElementById('btnUpdate').onclick=async()=>{
  if(!confirm('Pull latest from git and restart the agent service?')) return;
  try{
    const res=await fetch('/api/update',{method:'POST'}).then(r=>r.json());
    add('bot', res.ok ? (res.message||('Updated to v'+(res.version||'?'))) : ('Update failed: '+(res.message||res.error||'?')));
    if(res.version){window._ver=res.version; updateStatus();}
  }catch(e){add('bot','Update error: '+e);}
};

document.getElementById('btnConfirm').onclick=async()=>{
  const body={};
  if(pendingIsSudo){
    body.password=sudoPass.value||'';
  }
  let res;
  try{
    res=await fetch('/api/confirm',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)
    }).then(r=>r.json());
  }finally{
    sudoPass.value=''; // discard password from the field
  }
  add('bot', res.ok?('Done.'+((res.stdout||res.stderr)?('\n'+(res.stdout||'')+(res.stderr?('\n'+res.stderr):'')):'')):(res.error||'Confirm failed'));
  refreshPending();
};
document.getElementById('btnCancel').onclick=async()=>{
  sudoPass.value='';
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
