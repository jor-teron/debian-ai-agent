"""
LLM providers: Gemini, OpenAI-compat, Anthropic, and chat dispatch.

Talks to cloud APIs and local OpenAI-compatible runtimes (Ollama,
llama.cpp) via stdlib urllib, and runs tool-call loops. Provider
catalogs live in providers.py (re-exported through config).

Imports from: config.py (catalog, keys, defaults, base URLs), tools.py
              (TOOL_DECLS, tool-schema helpers, dispatch, build_system).
Used by: server.py (run_chat), tools.py (plain chat for jobs, _http_json
         for web_search).
"""
import json
import urllib.error
import urllib.request
from config import (
    DEFAULT_PROVIDER,
    GEMINI_API_BASE,
    PROVIDERS,
    allowed,
    default_model,
    default_provider,
    get_provider_meta,
    provider_key,
    provider_openai_base,
)
from tools import TOOL_DECLS, anthropic_tools, build_system, dispatch, openai_tools


# ---------------------------------------------------------------------------
# Shared HTTP helper
# ---------------------------------------------------------------------------


def _http_json(url, body, headers, timeout=90):
    """POST JSON and parse the JSON reply. Raises on HTTP/network errors."""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Plain chat (no tools) — used by scheduled jobs in tools.py
# ---------------------------------------------------------------------------


def _plain_chat(prompt, provider=None, model=None):
    """Short call without tools (for scheduled jobs)."""
    provider = provider or default_provider()
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    model = allowed(provider, model or default_model(provider))
    meta = get_provider_meta(provider) or PROVIDERS[provider]
    kind = meta["kind"]
    needs_key = bool(meta.get("needs_key", True))
    key = provider_key(provider)
    if needs_key and not key:
        return {"ok": False, "error": "No API key for %s" % provider, "reply": ""}
    try:
        if kind == "gemini":
            url = "%s/models/%s:generateContent?key=%s" % (GEMINI_API_BASE, model, key)
            data = _http_json(
                url,
                {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 1024},
                },
                {"Content-Type": "application/json"},
                timeout=60,
            )
            parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
            texts = [p.get("text", "") for p in parts if "text" in p]
            reply = "\n".join(texts).strip() or "(No text)"
            return {"ok": True, "reply": reply, "model": model, "provider": provider}
        if kind == "openai":
            # Cloud base from catalog, or local Ollama/llama.cpp OpenAI path.
            base = meta.get("base") or provider_openai_base(provider)
            url = base.rstrip("/") + "/chat/completions"
            headers = {"Content-Type": "application/json"}
            # Local runtimes need no real key; send a dummy bearer some servers expect.
            headers["Authorization"] = "Bearer %s" % (key or "local")
            data = _http_json(
                url,
                {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1024,
                },
                headers,
                timeout=60,
            )
            msg = ((data.get("choices") or [{}])[0].get("message") or {})
            reply = (msg.get("content") or "").strip() or "(No text)"
            return {"ok": True, "reply": reply, "model": model, "provider": provider}
        if kind == "anthropic":
            url = meta["base"].rstrip("/") + "/messages"
            data = _http_json(
                url,
                {
                    "model": model,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
                {
                    "Content-Type": "application/json",
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=60,
            )
            texts = [
                b.get("text", "")
                for b in (data.get("content") or [])
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            reply = "\n".join(texts).strip() or "(No text)"
            return {"ok": True, "reply": reply, "model": model, "provider": provider}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "reply": ""}
    return {"ok": False, "error": "Unknown provider kind", "reply": ""}


# ---------------------------------------------------------------------------
# Gemini (generateContent + function calling)
# ---------------------------------------------------------------------------


def gemini_chat(message, model, history):
    """Chat with Gemini, running workspace tools until the model replies in text."""
    key = provider_key("gemini")
    if not key:
        return {
            "ok": False,
            "error": "GEMINI_API_KEY missing. Copy .env.example to .env and add your key.",
            "reply": "",
            "tools": [],
            "provider": "gemini",
        }

    model = allowed("gemini", model)
    contents = []
    for turn in (history or [])[-16:]:
        role = "user" if turn.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": turn.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    url = "%s/models/%s:generateContent?key=%s" % (GEMINI_API_BASE, model, key)
    tool_trace = []
    reply = ""
    system = build_system()

    for _ in range(6):
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "tools": [{"function_declarations": TOOL_DECLS}],
        }
        try:
            data = _http_json(url, body, {"Content-Type": "application/json"}, timeout=90)
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")[:800]
            return {
                "ok": False,
                "error": "Gemini HTTP %s: %s" % (e.code, err),
                "reply": "",
                "tools": tool_trace,
                "model": model,
                "provider": "gemini",
            }
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(e),
                "reply": "",
                "tools": tool_trace,
                "model": model,
                "provider": "gemini",
            }

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

    return {"ok": True, "reply": reply, "tools": tool_trace, "model": model, "provider": "gemini"}


# ---------------------------------------------------------------------------
# OpenAI-compatible Chat Completions (OpenAI, xAI, DeepSeek, Ollama, llama.cpp)
# ---------------------------------------------------------------------------

# Curated tiny offline models that reject OpenAI tool schemas (Ollama 400:
# "does not support tools"). Match flexibly: ignore registry path and :tag.
_NO_TOOLS_MODEL_FRAGMENTS = ("tinydolphin", "tinyllama")


def _model_lacks_tool_support(model, meta=None):
    """True when we should skip tools up front (known tiny / supports_tools=False)."""
    meta = meta or {}
    if meta.get("supports_tools") is False:
        return True
    mid = (model or "").lower()
    # e.g. registry.ollama.ai/library/tinydolphin:latest → tinydolphin
    leaf = mid.rsplit("/", 1)[-1]
    name = leaf.split(":", 1)[0]
    for frag in _NO_TOOLS_MODEL_FRAGMENTS:
        if frag in mid or frag == name:
            return True
    return False


def _http_err_no_tools(err_text):
    """True if the server rejected the request because the model has no tools."""
    return "does not support tools" in (err_text or "").lower()


def openai_compat_chat(provider, message, model, history):
    """Chat with an OpenAI-style API, running workspace tools as tool_calls.

    Used for cloud OpenAI-compat providers and offline Ollama / llama.cpp
    (local base URL from providers.provider_openai_base; no API key required).

    Small local models (tinydolphin, tinyllama, …) often reject tool schemas.
    We skip tools for known no-tool names / supports_tools=False, and if any
    model returns "does not support tools", retry once without tools/tool_choice
    (plain messages + system prompt, empty tools trace, no tool loop).
    """
    meta = get_provider_meta(provider) or PROVIDERS[provider]
    needs_key = bool(meta.get("needs_key", True))
    key = provider_key(provider)
    if needs_key and not key:
        return {
            "ok": False,
            "error": "%s missing. Add it to .env." % (meta.get("env_key") or "API key"),
            "reply": "",
            "tools": [],
            "provider": provider,
        }

    model = allowed(provider, model)
    messages = [{"role": "system", "content": build_system()}]
    for turn in (history or [])[-16:]:
        role = "user" if turn.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": turn.get("content", "")})
    messages.append({"role": "user", "content": message})

    # Resolved base includes /v1 for local Ollama and llama.cpp servers.
    base = meta.get("base") or provider_openai_base(provider)
    url = base.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        # Offline: dummy bearer; online: real key from .env.
        "Authorization": "Bearer %s" % (key or "local"),
    }
    # OpenRouter asks for these optional attribution headers on free/paid routes.
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/jor-teron/debian-ai-agent"
        headers["X-Title"] = "AI-Agent"
    tool_trace = []
    reply = ""

    # Skip tools for known tiny offline models (avoid a wasted 400). Larger
    # offline models (llama3.2, mistral, …) still try with tools first.
    use_tools = not _model_lacks_tool_support(model, meta)
    no_tools_retry_done = False
    # Without tools: single completion only (no tool loop).
    rounds = 1 if not use_tools else 6
    i = 0
    while i < rounds:
        i += 1
        body = {
            "model": model,
            "messages": messages,
        }
        if use_tools:
            body["tools"] = openai_tools()
            body["tool_choice"] = "auto"
        try:
            data = _http_json(url, body, headers, timeout=90)
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")[:800]
            # Auto-fallback: model rejected tools → one plain retry (no tools).
            if use_tools and not no_tools_retry_done and _http_err_no_tools(err):
                use_tools = False
                no_tools_retry_done = True
                rounds = i + 1  # allow exactly one more attempt without tools
                continue
            return {
                "ok": False,
                "error": "%s HTTP %s: %s" % (provider, e.code, err),
                "reply": "",
                "tools": tool_trace,
                "model": model,
                "provider": provider,
            }
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(e),
                "reply": "",
                "tools": tool_trace,
                "model": model,
                "provider": provider,
            }

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""

        if not use_tools or not tool_calls:
            reply = (content or "").strip() or "(No text)"
            break

        # Append assistant turn (with tool_calls)
        messages.append(
            {
                "role": "assistant",
                "content": content if content else None,
                "tool_calls": tool_calls,
            }
        )
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                args = {}
            result = dispatch(name, args)
            tool_trace.append({"name": name, "args": args, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or name,
                    "content": json.dumps(result),
                }
            )
    else:
        reply = reply or "Stopped after too many tool steps."

    return {"ok": True, "reply": reply, "tools": tool_trace, "model": model, "provider": provider}


# ---------------------------------------------------------------------------
# Anthropic Messages API
# ---------------------------------------------------------------------------


def anthropic_chat(message, model, history):
    """Chat with Claude, running workspace tools as tool_use / tool_result."""
    meta = PROVIDERS["anthropic"]
    key = provider_key("anthropic")
    if not key:
        return {
            "ok": False,
            "error": "ANTHROPIC_API_KEY missing. Add it to .env.",
            "reply": "",
            "tools": [],
            "provider": "anthropic",
        }

    model = allowed("anthropic", model)
    messages = []
    for turn in (history or [])[-16:]:
        role = "user" if turn.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": turn.get("content", "")})
    messages.append({"role": "user", "content": message})

    url = meta["base"].rstrip("/") + "/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    tool_trace = []
    reply = ""
    system = build_system()

    for _ in range(6):
        body = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
            "tools": anthropic_tools(),
        }
        try:
            data = _http_json(url, body, headers, timeout=90)
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")[:800]
            return {
                "ok": False,
                "error": "Anthropic HTTP %s: %s" % (e.code, err),
                "reply": "",
                "tools": tool_trace,
                "model": model,
                "provider": "anthropic",
            }
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(e),
                "reply": "",
                "tools": tool_trace,
                "model": model,
                "provider": "anthropic",
            }

        content_blocks = data.get("content") or []
        tool_uses = [b for b in content_blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
        texts = [
            b.get("text", "")
            for b in content_blocks
            if isinstance(b, dict) and b.get("type") == "text"
        ]

        if not tool_uses:
            reply = "\n".join(texts).strip() or "(No text)"
            break

        messages.append({"role": "assistant", "content": content_blocks})
        result_blocks = []
        for tu in tool_uses:
            name = tu.get("name") or ""
            args = tu.get("input") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result = dispatch(name, args)
            tool_trace.append({"name": name, "args": args, "result": result})
            result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.get("id") or name,
                    "content": json.dumps(result),
                }
            )
        messages.append({"role": "user", "content": result_blocks})
    else:
        reply = reply or "Stopped after too many tool steps."

    return {
        "ok": True,
        "reply": reply,
        "tools": tool_trace,
        "model": model,
        "provider": "anthropic",
    }


# ---------------------------------------------------------------------------
# Dispatch by provider kind
# ---------------------------------------------------------------------------


def run_chat(message, provider=None, model=None, history=None):
    """Pick the right chat function from PROVIDERS[id].kind (online + offline)."""
    provider = (provider or default_provider() or DEFAULT_PROVIDER).lower().strip()
    if provider not in PROVIDERS:
        return {
            "ok": False,
            "error": "Unknown provider %r. Use one of: %s" % (provider, ", ".join(PROVIDERS)),
            "reply": "",
            "tools": [],
        }
    meta = PROVIDERS[provider]
    kind = meta["kind"]
    if kind == "gemini":
        return gemini_chat(message, model, history)
    if kind == "openai":
        return openai_compat_chat(provider, message, model, history)
    if kind == "anthropic":
        return anthropic_chat(message, model, history)
    return {"ok": False, "error": "Unsupported provider kind", "reply": "", "tools": []}
