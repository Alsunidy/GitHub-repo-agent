"""مصنع الـ LLM — نقطة واحدة يغيّر منها الطرفان المزوّد.

المزوّد يُضبط من متغيّر البيئة LLM_PROVIDER (الافتراضي: anthropic).
الوكلاء في المسار الثاني ينادون get_llm() مباشرة — لا يستوردون مزوّداً بعينه.
"""

import os

from dotenv import load_dotenv

load_dotenv()

_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
    "google": "gemini-2.0-flash",
}


class LLMUnavailable(RuntimeError):
    """المفتاح غير مضبوط أو المكتبة غير مثبّتة أو المزوّد غير معروف."""


def get_llm(temperature: float = 0.0, **kwargs):
    """يرجع chat model جاهزاً حسب LLM_PROVIDER.

    يرمي LLMUnavailable برسالة واضحة بدل أن يفشل بغموض داخل node.
    """
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    model = os.getenv("LLM_MODEL") or _MODELS.get(provider)

    if provider == "anthropic":
        _require_key("ANTHROPIC_API_KEY", provider)
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:  # pragma: no cover - رسالة تركيب
            raise LLMUnavailable("pip install langchain-anthropic") from exc
        return ChatAnthropic(model=model, temperature=temperature, **kwargs)

    if provider == "openai":
        _require_key("OPENAI_API_KEY", provider)
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMUnavailable("pip install langchain-openai") from exc
        return ChatOpenAI(model=model, temperature=temperature, **kwargs)

    if provider == "google":
        _require_key("GOOGLE_API_KEY", provider)
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:  # pragma: no cover
            raise LLMUnavailable("pip install langchain-google-genai") from exc
        return ChatGoogleGenerativeAI(model=model, temperature=temperature, **kwargs)

    raise LLMUnavailable(
        f"LLM_PROVIDER={provider!r} غير معروف — المتاح: {', '.join(_MODELS)}"
    )


def _require_key(var: str, provider: str) -> None:
    if not os.getenv(var):
        raise LLMUnavailable(f"{var} غير مضبوط في البيئة (مطلوب لـ {provider})")
