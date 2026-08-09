# وثيقة العقود — GitHub Repo Health Agent

> هذه الوثيقة يُتفق عليها **قبل** بدء الكود. أي تعديل عليها لاحقاً = إبلاغ فوري للطرف الآخر.
> الهدف: كل طرف يبني قطعته وهو يعرف شكل قطعة الآخر بالضبط، بدون انتظار.

---

## العقد الأول: الـ State

```python
# backend/state.py
import operator
from typing import Annotated, Optional, TypedDict


class AgentState(TypedDict):
    # --- المدخلات ---
    repo_url: str                 # الرابط كما أدخله المستخدم
    language: str                 # "en" | "ar" — لغة التقرير والرسائل

    # --- يملؤها الحارس (Guardrail) ---
    owner: str                    # اسم المالك من الرابط
    repo: str                     # اسم المستودع من الرابط
    rejection_reason: Optional[str]   # نص الرفض، أو None لو الطلب سليم

    # --- تملؤها أداة الجلب (تُكتب مرة واحدة) ---
    repo_data: dict               # انظر "شكل repo_data" أدناه

    # --- يقررها المشرف (Supervisor) في كل دورة ---
    next_agent: str               # "security" | "issues" | "docs" | "done"

    # --- تتراكم (Annotated + operator.add) ---
    agents_done: Annotated[list[str], operator.add]      # أسماء الوكلاء المنفَّذين
    findings: Annotated[list[dict], operator.add]        # انظر "شكل finding" أدناه

    # --- المخرجات النهائية ---
    report: str                   # تقرير Markdown بلغة المستخدم
    issue_url: Optional[str]      # رابط البلاغ بعد فتحه، أو None
```

### شكل `repo_data`
```python
{
    "meta": {
        "full_name": str,          # "owner/repo"
        "description": str | None,
        "stars": int,
        "pushed_at": str,          # ISO date
        "language": str | None,
    },
    "readme": str,                 # نص README (فارغ "" لو غير موجود)
    "open_issues": [               # أحدث 30 بلاغاً مفتوحاً
        {
            "number": int,
            "title": str,
            "body": str,
            "created_at": str,     # ISO date
            "comments": int,
            "labels": list[str],
        }
    ],
    "dependency_files": {          # اسم الملف -> محتواه (قد يكون فارغاً {})
        "requirements.txt": str,
    },
    "code_files": {                # ملفات كود لفحص المفاتيح المكشوفة
        "path/to/file.py": str,
    },
}
```

### شكل `finding` (كل وكيل يضيف عنصراً واحداً على الأقل)
```python
{
    "agent": str,        # "security" | "issues" | "docs"
    "severity": str,     # "critical" | "high" | "medium" | "low" | "none"
    "title": str,        # عنوان قصير للمشكلة
    "detail": str,       # الشرح (نص أو Markdown)
    "evidence": list[str],   # أدلة: معرّفات GHSA/CVE، أرقام بلاغات، أسماء أقسام ناقصة
}
```

---

## العقد الثاني: تواقيع الأدوات

> كل دالة **مستقلة تماماً** — تُختبر بسكربت صغير بدون الـ graph.

```python
# backend/tools/github_tools.py

def parse_repo_url(url: str) -> tuple[str, str] | None:
    """يرجع (owner, repo) لو الرابط رابط مستودع GitHub صالح، وإلا None."""


def fetch_repo_data(owner: str, repo: str) -> dict:
    """يرجع dict بشكل repo_data أعلاه.
    يرمي RepoNotFound لو المستودع غير موجود أو خاص."""


def open_issue(owner: str, repo: str, title: str, body: str) -> str:
    """يفتح بلاغاً فعلياً ويرجع رابطه (html_url).
    يرمي MissingToken لو GITHUB_TOKEN غير مضبوط."""


class RepoNotFound(Exception): ...
class MissingToken(Exception): ...
```

```python
# backend/tools/osv_tools.py

def parse_requirements(text: str) -> list[tuple[str, str]]:
    """يستخرج أزواج (package, version) من الأسطر المثبّتة بـ == فقط."""


def check_vulnerabilities(requirements_text: str, limit: int = 10) -> list[dict]:
    """يستعلم OSV.dev لكل حزمة. يرجع قائمة عناصر بالشكل:
    {"package": str, "version": str, "vuln_ids": list[str], "summary": str}
    وعند فشل الاستعلام لحزمة:
    {"package": str, "version": str, "error": str}
    لا يرمي استثناءً — الأخطاء تُسجَّل داخل النتائج."""
```

```python
# backend/tools/secret_tools.py

def scan_secrets(code_files: dict[str, str]) -> list[dict]:
    """يفحص محتوى الملفات بأنماط معروفة (ghp_, sk-, AKIA...).
    يرجع: {"file": str, "line": int, "kind": str, "snippet": str}
    (snippet مقنَّع جزئياً — لا يُظهر المفتاح كاملاً)."""
```

---

## العقد الثالث: واجهة الـ API

> الواجهة تتخاطب مع الخادم عبر HTTP فقط — لا تستورد الـ graph إطلاقاً.

### `POST /analyze`
```jsonc
// الطلب
{ "repo_url": "https://github.com/owner/repo", "language": "en" }

// الرد — حالة النجاح (النظام متوقف عند الموافقة البشرية)
{
  "thread_id": "uuid-string",
  "status": "awaiting_approval",
  "report": "## Executive summary\n...",
  "agents_done": ["security", "issues", "docs"]
}

// الرد — حالة الرفض (رابط غير صالح / مستودع غير موجود)
{
  "thread_id": "uuid-string",
  "status": "rejected",
  "report": "نص الرفض المؤدب",
  "agents_done": []
}
```

### `POST /approve`
```jsonc
// الطلب
{ "thread_id": "uuid-string", "approved": true }

// الرد — بعد الموافقة
{ "status": "done", "issue_url": "https://github.com/owner/repo/issues/12" }

// الرد — بعد الرفض
{ "status": "cancelled", "issue_url": null }
```

### `GET /health`
```jsonc
{ "status": "ok" }
```

---

## قواعد العمل المتوازي

1. **الملفات مفصولة:** لا يعدّل الطرفان الملف نفسه. (الـ graph/backend لطرف، الأدوات/الواجهة للطرف الآخر.)
2. **Stubs مؤقتة:** من ينتظر قطعة الآخر يكتب نسخة وهمية بسيطة بنفس التوقيع ويكمل عليها — **وتُحذف كلها قبل التسليم** (البريف يمنع الأدوات الوهمية في النسخة النهائية).
3. **أي تعديل على هذه الوثيقة = إبلاغ فوري.** تغيير شكل مخرجات دالة بدون إبلاغ هو السبب الأول لتعطل الفرق.
4. **نقاط الالتقاء ثلاث فقط:** (أ) الاتفاق على هذه الوثيقة، (ب) ربط الأدوات الحقيقية بالـ graph، (ج) ربط الواجهة بالخادم الحقيقي.
