"""مصنع الـ LLM — نقطة واحدة ينادي منها الطرفان النموذج.

الوكلاء في المسار الثاني ينادون get_llm() ولا يبنون ChatOpenAI بأنفسهم:
تغيير الموديل أو الإعدادات يبقى في ملف واحد.
"""

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "gpt-4o-mini"

# بادئات مفاتيح مزوّدين آخرين. لصق أحدها في OPENAI_API_KEY يُرجع 401 مبهماً
# من OpenAI، فنكشفه هنا برسالة مفهومة بدل انتظار الفشل داخل node.
_FOREIGN_KEY_PREFIXES = {"sk-or-": "OpenRouter", "sk-ant-": "Anthropic"}


class LLMUnavailable(RuntimeError):
    """المفتاح غير مضبوط أو غير صالح أو المكتبة غير مثبّتة."""


def get_llm(temperature: float = 0.0, **kwargs):
    """يرجع chat model جاهزاً.

    يرمي LLMUnavailable برسالة واضحة بدل أن يفشل بغموض داخل node.
    """
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise LLMUnavailable("OPENAI_API_KEY غير مضبوط في البيئة (ضعه في .env)")

    for prefix, owner in _FOREIGN_KEY_PREFIXES.items():
        if key.startswith(prefix):
            raise LLMUnavailable(
                f"OPENAI_API_KEY يبدأ بـ {prefix} ⇒ هذا مفتاح {owner}، لا OpenAI. "
                f"مفاتيح OpenAI تبدأ بـ sk- أو sk-proj-"
            )

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - رسالة تركيب
        raise LLMUnavailable("pip install langchain-openai") from exc

    model = os.getenv("LLM_MODEL") or DEFAULT_MODEL
    return ChatOpenAI(model=model, temperature=temperature, api_key=key, **kwargs)
