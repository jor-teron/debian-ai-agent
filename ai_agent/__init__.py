"""
linux-ai-agent — stdlib-only personal AI agent package.

Install surface stays at the repo root (run.sh, .env, VERSION, …).
All Python code and editable prompt/model/UI assets live here.
"""

__all__ = ["__version__"]


def __getattr__(name):
    # Lazy so `import ai_agent` stays cheap and does not pull the whole stack.
    if name == "__version__":
        from ai_agent.config import app_version

        return app_version()
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
