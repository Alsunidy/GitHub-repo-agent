"""العقد الأول — الـ State المشترك بين كل الـ nodes.

هذا الملف يملكه المسار الأول. أي تغيير على أسماء الحقول أو أنواعها
يستوجب إبلاغ الطرف الآخر فوراً (قاعدة العقود رقم 3).
"""

import operator
from typing import Annotated, Optional, TypedDict


class AgentState(TypedDict):
    """حالة تحليل مستودع واحد، من الرابط حتى فتح البلاغ."""

    # --- المدخلات ---
    repo_url: str                 # الرابط كما أدخله المستخدم
    language: str                 # "en" | "ar" — لغة التقرير والرسائل

    # --- يملؤها الحارس (Guardrail) ---
    owner: str                    # اسم المالك من الرابط
    repo: str                     # اسم المستودع من الرابط
    rejection_reason: Optional[str]   # نص الرفض، أو None لو الطلب سليم

    # --- تملؤها أداة الجلب (تُكتب مرة واحدة) ---
    repo_data: dict               # انظر "شكل repo_data" في CONTRACTS.md

    # --- يقررها المشرف (Supervisor) في كل دورة ---
    next_agent: str               # "security" | "issues" | "docs" | "done"

    # --- تتراكم (Annotated + operator.add) ---
    agents_done: Annotated[list[str], operator.add]      # أسماء الوكلاء المنفَّذين
    findings: Annotated[list[dict], operator.add]        # انظر "شكل finding"

    # --- المخرجات النهائية ---
    report: str                   # تقرير Markdown بلغة المستخدم
    issue_url: Optional[str]      # رابط البلاغ بعد فتحه، أو None

    # --- إضافة للعقد: الموافقة البشرية (HITL) ---
    # بدون هذه الحقول لا يستطيع /approve معرفة ماذا يفتح.
    # إضافية بالكامل: لا تكسر أي حقل كان الطرف الآخر يعتمد عليه.
    issue_title: str              # عنوان البلاغ المقترح، يعرضه الـ UI قبل الموافقة
    issue_body: str               # نص البلاغ المقترح (مختصر من التقرير)
    approved: Optional[bool]      # None = لم يُسأل بعد | True = وافق | False = رفض

    # --- إضافة للعقد: أثر قرارات المشرف (للديمو والتتبّع) ---
    # البريف يطلب إظهار التتبّع في الديمو: "أو حالتك المسجّلة".
    supervisor_log: Annotated[list[str], operator.add]


def initial_state(repo_url: str, language: str = "en") -> AgentState:
    """حالة ابتدائية كاملة — كل الحقول موجودة حتى لا يفشل أي node على مفتاح ناقص."""
    return AgentState(
        repo_url=repo_url,
        language=language if language in ("en", "ar") else "en",
        owner="",
        repo="",
        rejection_reason=None,
        repo_data={},
        next_agent="",
        agents_done=[],
        findings=[],
        report="",
        issue_url=None,
        issue_title="",
        issue_body="",
        approved=None,
        supervisor_log=[],
    )
