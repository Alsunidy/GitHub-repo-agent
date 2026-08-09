"""مصنع الـ LLM — نقطة واحدة يغيّر منها الطرفان المزوّد.

المزوّد يُضبط من متغيّر البيئة LLM_PROVIDER (الافتراضي: openai).
الوكلاء في المسار الثاني ينادون get_llm() مباشرة — لا يستوردون مزوّداً بعينه.

ملاحظة على openrouter: بوابة متوافقة مع واجهة OpenAI، فنستخدم ChatOpenAI نفسه
مع base_url مختلف. مفاتيحه تبدأ بـ sk-or-v1 وترفضها OpenAI مباشرةً بـ 401 —
لو رأيت ذلك الخطأ فالمفتاح من OpenRouter وليس من OpenAI.
"""

import os

from dotenv import load_dotenv

load_dotenv()

_MODELS = {
    "openai": "gpt-4o-mini",
    "openrouter": "openai/gpt-4o-mini",   # أسماء موديلات OpenRouter تحمل بادئة المزوّد
    "anthropic": "claude-sonnet-4-5",
    "google": "gemini-2.0-flash",
}

_KEY_VARS = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
}

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class LLMUnavailable(RuntimeError):
    """المفتاح غير مضبوط أو المكتبة غير مثبّتة أو المزوّد غير معروف."""


def get_llm(temperature: float = 0.0, **kwargs):
    """يرجع chat model جاهزاً حسب LLM_PROVIDER.

    يرمي LLMUnavailable برسالة واضحة بدل أن يفشل بغموض داخل node.
    """
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    model = os.getenv("LLM_MODEL") or _MODELS.get(provider)

    if provider in ("openrouter", "openai"):
        key = _require_key(_KEY_VARS[provider], provider)
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # pragma: no cover - رسالة تركيب
            raise LLMUnavailable("pip install langchain-openai") from exc
        if provider == "openrouter":
            kwargs.setdefault("base_url", os.getenv("OPENROUTER_BASE_URL", _OPENROUTER_BASE_URL))
        return ChatOpenAI(model=model, temperature=temperature, api_key=key, **kwargs)

    if provider == "anthropic":
        key = _require_key("ANTHROPIC_API_KEY", provider)
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:  # pragma: no cover
            raise LLMUnavailable("pip install langchain-anthropic") from exc
        return ChatAnthropic(model=model, temperature=temperature, api_key=key, **kwargs)

    if provider == "google":
        key = _require_key("GOOGLE_API_KEY", provider)
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:  # pragma: no cover
            raise LLMUnavailable("pip install langchain-google-genai") from exc
        return ChatGoogleGenerativeAI(
            model=model, temperature=temperature, google_api_key=key, **kwargs
        )

    raise LLMUnavailable(
        f"LLM_PROVIDER={provider!r} غير معروف — المتاح: {', '.join(_MODELS)}"
    )


def _require_key(var: str, provider: str) -> str:
    key = os.getenv(var)
    if not key:
        raise LLMUnavailable(f"{var} غير مضبوط في البيئة (مطلوب لـ {provider})")
    return key
