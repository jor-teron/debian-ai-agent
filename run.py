#!/usr/bin/env python3
"""
Minimal personal AI agent for Debian.

- Stdlib only (no pip / venv / Apache)
- Local chat page at http://127.0.0.1:8787
- Gemini API key from .env (never sent to the browser)
- Simple file + shell tools jailed to ./agent-workspace
"""
import json
import sys
import os
import re
import subprocess
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

# Refuse Python 2 / ancient 3.x early (clear message for mixed systems)
if sys.version_info[0] < 3:
    sys.stderr.write("This app needs Python 3. You ran Python %s.\n" % sys.version.split()[0])
    sys.stderr.write("Try:  python3 run.py   or   ./run.sh\n")
    sys.exit(1)
if sys.version_info < (3, 8):
    sys.stderr.write("Need Python 3.8+. You have %s\n" % sys.version.split()[0])
    sys.stderr.write("Try:  python3 run.py   or   ./run.sh\n")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT / "agent-workspace"
ENV_PATH = ROOT / ".env"
HOST, PORT = "127.0.0.1", 8787

FREE_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
]
PAID_MODELS = [
    "gemini-2.5-pro",
    "gemini-1.5-pro",
]
DEFAULT_MODEL = "gemini-2.0-flash"
API_BASE = "https://generativelanguage.googleapis.com/v1beta"

BLOCKED = re.compile(
    r"(?ix)(rm\s+-rf\s+/)|(mkfs\b)|(\bdd\b.*\bof=/dev/)|(shutdown\b)|(reboot\b)|(poweroff\b)"
)

SYSTEM = (
    "You are a helpful agent on the user's Linux PC. "
    "You may use tools to list/read/write files and run shell commands "
    "inside the workspace folder. Keep answers short and clear."
)

HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AI Agent</title>
<style>
body{margin:0;font-family:system-ui,sans-serif;background:#0f1419;color:#e7ecf3;display:flex;flex-direction:column;min-height:100vh}
header{padding:12px 16px;background:#1a2332;display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between}
h1{font-size:1.05rem;margin:0}
.controls{display:flex;gap:8px;flex-wrap:wrap;align-items:end}
label{font-size:.75rem;color:#9aa8bc;display:block}
select,button,textarea{font:inherit;border-radius:8px;border:1px solid #2a3548;background:#0c1118;color:#e7ecf3}
select{padding:6px 8px}
#status{font-size:.8rem;color:#9aa8bc}
#status.ok{color:#6ee7b7}#status.bad{color:#f87171}
#log{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.msg{max-width:820px;padding:10px 12px;border-radius:12px;white-space:pre-wrap;line-height:1.4}
.user{align-self:flex-end;background:#243247}
.bot{align-self:flex-start;background:#1a2332;border:1px solid #2a3548}
.tools{margin-top:6px;font-size:.75rem;color:#9aa8bc}
form{display:flex;gap:8px;padding:12px;background:#1a2332;border-top:1px solid #2a3548}
textarea{flex:1;min-height:44px;padding:8px}
button{padding:10px 14px;background:#60a5fa;border:none;color:#041018;font-weight:600}
button:disabled{opacity:.5}
</style></head><body>
<header>
  <h1>AI Agent</h1>
  <div class="controls">
    <div><label>Category</label>
      <select id="tier"><option value="free" selected>Free</option><option value="paid">Paid</option></select>
    </div>
    <div><label>Model</label><select id="model"></select></div>
    <div id="status">…</div>
  </div>
</header>
<div id="log"></div>
<form id="f"><textarea id="input" placeholder="Ask something…" required></textarea>
<button id="send">Send</button></form>
<script>
const log=document.getElementById('log'),tier=document.getElementById('tier'),model=document.getElementById('model');
const status=document.getElementById('status'),input=document.getElementById('input'),send=document.getElementById('send');
let catalog={free:[],paid:[],default:'gemini-2.0-flash'}, history=[];
function fill(){const list=catalog[tier.value]||[]; model.innerHTML='';
  list.forEach(m=>{const o=document.createElement('option');o.value=m;o.textContent=m;model.appendChild(o);});
  const s=localStorage.getItem('m'); if(s&&list.includes(s)) model.value=s; else if(list.includes(catalog.default)) model.value=catalog.default; else if(list[0]) model.value=list[0];
}
function add(role,text,tools){const d=document.createElement('div'); d.className='msg '+(role==='user'?'user':'bot'); d.textContent=text;
  if(tools&&tools.length){const x=document.createElement('details'); x.className='tools'; x.innerHTML='<summary>'+tools.length+' tool(s)</summary><pre>'+JSON.stringify(tools,null,2)+'</pre>'; d.appendChild(x);}
  log.appendChild(d); log.scrollTop=log.scrollHeight;}
async function boot(){
  try{
    const h=await fetch('/api/health').then(r=>r.json());
    status.textContent=h.api_key_set?'API key OK':'API key missing — edit .env'; status.className=h.api_key_set?'ok':'bad';
    const m=await fetch('/api/models').then(r=>r.json());
    catalog={free:m.categories.free,paid:m.categories.paid,default:m.default};
    const t=localStorage.getItem('t'); if(t==='paid'||t==='free') tier.value=t; fill();
  }catch(e){status.textContent='Cannot reach server'; status.className='bad';}
}
tier.onchange=()=>{localStorage.setItem('t',tier.value); fill();};
model.onchange=()=>localStorage.setItem('m',model.value);
document.getElementById('f').onsubmit=async ev=>{
  ev.preventDefault(); const message=input.value.trim(); if(!message) return;
  add('user',message); input.value=''; send.disabled=true;
  try{
    const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message,model:model.value,history})});
    const data=await res.json();
    if(!data.ok) add('bot', data.error||'Failed', data.tools); else {
      add('bot', data.reply, data.tools);
      history.push({role:'user',content:message},{role:'assistant',content:data.reply});
      if(history.length>20) history=history.slice(-20);
    }
  }catch(e){add('bot','Network error: '+e);} finally{send.disabled=false; input.focus();}
};
boot();
</script></body></html>
"""


def load_env():
    out = {}  # type: Dict[str, str]
    if not ENV_PATH.exists():
        return out
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def api_key() -> str:
    return (load_env().get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()


def default_model() -> str:
    return (load_env().get("GEMINI_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def allowed(model):
    all_m = set(FREE_MODELS) | set(PAID_MODELS)
    if model and model in all_m:
        return model
    d = default_model()
    return d if d in all_m else FREE_MODELS[0]


def ensure_ws() -> None:
    WORKSPACE.mkdir(parents=True, exist_ok=True)


def safe_path(user_path: str) -> Path:
    raw = Path(user_path).expanduser()
    cand = (WORKSPACE / raw).resolve() if not raw.is_absolute() else raw.resolve()
    try:
        cand.relative_to(WORKSPACE.resolve())
    except ValueError as e:
        raise PermissionError("Path outside agent-workspace/") from e
    return cand


def tool_list_dir(path: str = ".") -> dict:
    ensure_ws()
    t = safe_path(path)
    if not t.is_dir():
        return {"ok": False, "error": f"Not a directory: {t}"}
    entries = [{"name": c.name, "type": "dir" if c.is_dir() else "file"} for c in sorted(t.iterdir())]
    return {"ok": True, "path": str(t), "entries": entries}


def tool_read_file(path: str) -> dict:
    ensure_ws()
    t = safe_path(path)
    if not t.is_file():
        return {"ok": False, "error": f"Not a file: {t}"}
    data = t.read_bytes()[:200_000]
    return {"ok": True, "path": str(t), "content": data.decode("utf-8", errors="replace")}


def tool_write_file(path: str, content: str) -> dict:
    ensure_ws()
    t = safe_path(path)
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(t)}


def tool_run_shell(command: str) -> dict:
    ensure_ws()
    cmd = (command or "").strip()
    if not cmd:
        return {"ok": False, "error": "Empty command"}
    if BLOCKED.search(cmd) or cmd.startswith("sudo"):
        return {"ok": False, "error": "Command blocked for safety"}
    try:
        p = subprocess.run(
            cmd, shell=True, cwd=str(WORKSPACE), capture_output=True, text=True, timeout=30
        )
        return {
            "ok": p.returncode == 0,
            "exit_code": p.returncode,
            "stdout": p.stdout[-40000:],
            "stderr": p.stderr[-10000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timed out"}


TOOLS = {
    "list_dir": tool_list_dir,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "run_shell": tool_run_shell,
}

TOOL_DECLS = [
    {
        "name": "list_dir",
        "description": "List files in the workspace",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
    },
    {
        "name": "read_file",
        "description": "Read a text file in the workspace",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write a text file in the workspace",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_shell",
        "description": "Run a shell command with cwd=workspace (no sudo)",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
]


def dispatch(name, args):
    try:
        if name == "list_dir":
            return tool_list_dir(args.get("path") or ".")
        if name == "read_file":
            return tool_read_file(args["path"])
        if name == "write_file":
            return tool_write_file(args["path"], args.get("content", ""))
        if name == "run_shell":
            return tool_run_shell(args["command"])
        return {"ok": False, "error": f"Unknown tool {name}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def gemini_chat(message, model, history):
    key = api_key()
    if not key:
        return {"ok": False, "error": "GEMINI_API_KEY missing. Copy .env.example to .env and add your key.", "reply": "", "tools": []}

    model = allowed(model)
    contents = []
    for turn in (history or [])[-16:]:
        role = "user" if turn.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": turn.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    url = f"{API_BASE}/models/{model}:generateContent?key={key}"
    tool_trace = []
    reply = ""

    for _ in range(6):
        body = {
            "system_instruction": {"parts": [{"text": SYSTEM}]},
            "contents": contents,
            "tools": [{"function_declarations": TOOL_DECLS}],
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")[:800]
            return {"ok": False, "error": f"Gemini HTTP {e.code}: {err}", "reply": "", "tools": tool_trace, "model": model}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e), "reply": "", "tools": tool_trace, "model": model}

        parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
        fn_calls, texts = [], []
        for p in parts:
            if "functionCall" in p:
                fn_calls.append(p["functionCall"])
            elif "text" in p:
                texts.append(p["text"])

        if not fn_calls:
            reply = "\n".join(texts).strip() or "(No text)"
            break

        contents.append({"role": "model", "parts": parts})
        response_parts = []
        for fc in fn_calls:
            name = fc.get("name") or ""
            args = fc.get("args") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result = dispatch(name, args)
            tool_trace.append({"name": name, "args": args, "result": result})
            response_parts.append({"functionResponse": {"name": name, "response": result}})
        contents.append({"role": "user", "parts": response_parts})
    else:
        reply = reply or "Stopped after too many tool steps."

    return {"ok": True, "reply": reply, "tools": tool_trace, "model": model}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter terminal
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _send(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        raw = json.dumps(obj).encode("utf-8")
        self._send(code, raw, "application/json; charset=utf-8")

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/health":
            self._json(200, {"ok": True, "api_key_set": bool(api_key()), "workspace": str(WORKSPACE)})
            return
        if path == "/api/models":
            self._json(
                200,
                {
                    "categories": {"free": FREE_MODELS, "paid": PAID_MODELS},
                    "default": allowed(default_model()),
                },
            )
            return
        self._json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/api/chat":
            self._json(404, {"ok": False, "error": "Not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "Invalid JSON"})
            return
        message = (data.get("message") or "").strip()
        if not message:
            self._json(400, {"ok": False, "error": "message required"})
            return
        result = gemini_chat(message, data.get("model"), data.get("history") or [])
        self._json(200 if result.get("ok") else 400, result)


def main():
    ensure_ws()
    if not ENV_PATH.exists() and (ROOT / ".env.example").exists():
        print("Tip: copy .env.example to .env and add GEMINI_API_KEY")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Open http://{HOST}:{PORT}  (Ctrl+C to stop)")
    if not api_key():
        print("WARNING: GEMINI_API_KEY not set in .env yet")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
