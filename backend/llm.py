"""LLM factory -- the single place either track reaches for a model.

Agents in track 2 call get_llm() rather than building ChatOpenAI themselves,
so changing the model or its settings stays in one file.
"""

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "gpt-4o-mini"

# Key prefixes belonging to other providers. Pasting one of these into
# OPENAI_API_KEY produces an opaque 401 from OpenAI, so we catch it here with
# a message that says what is actually wrong.
_FOREIGN_KEY_PREFIXES = {"sk-or-": "OpenRouter", "sk-ant-": "Anthropic"}


class LLMUnavailable(RuntimeError):
    """The key is missing or invalid, or the package is not installed."""


def get_llm(temperature: float = 0.0, **kwargs):
    """Return a ready chat model.

    Raises LLMUnavailable with a clear message rather than failing obscurely
    somewhere inside a node.
    """
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise LLMUnavailable("OPENAI_API_KEY is not set (put it in .env)")

    for prefix, owner in _FOREIGN_KEY_PREFIXES.items():
        if key.startswith(prefix):
            raise LLMUnavailable(
                f"OPENAI_API_KEY starts with {prefix}, so it is an {owner} key, "
                f"not an OpenAI one. OpenAI keys start with sk- or sk-proj-"
            )

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - install hint
        raise LLMUnavailable("pip install langchain-openai") from exc

    model = os.getenv("LLM_MODEL") or DEFAULT_MODEL
    return ChatOpenAI(model=model, temperature=temperature, api_key=key, **kwargs)
