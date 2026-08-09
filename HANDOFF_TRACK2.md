# تسليم المسار الثاني → المسار الأول

> الأدوات الثلاث جاهزة ومُختبرة فعلياً (لا stubs)، بتواقيع مطابقة لـ `CONTRACTS.md`
> مع تعديل واحد على شكل مخرجات `check_vulnerabilities` (بند ٢). الوكلاء الثلاثة
> وnode التقرير والواجهة لم تُبنَ بعد.

---

## ١. ما اكتمل

### `backend/tools/github_tools.py`
```python
def parse_repo_url(url: str) -> tuple[str, str] | None: ...
def fetch_repo_data(owner: str, repo: str) -> dict: ...          # يرمي RepoNotFound
def open_issue(owner: str, repo: str, title: str, body: str) -> str: ...  # يرمي MissingToken
```
اختبار فعلي على `sl-rwl/test_1`: `full_name`, `open_issues=1`, `readme=12` حرفاً،
`dependency_files=['requirements.txt']`, `code_files=1` (`app.py`). واختبار فشل
فعلي على مستودع غير موجود (`sl-rwl/demo-shop`) رمى `RepoNotFound` بشكل صحيح.

### `backend/tools/osv_tools.py`
```python
def parse_requirements(text: str) -> list[tuple[str, str]]: ...
def check_vulnerabilities(requirements_text: str, limit: int = 10) -> list[dict]: ...  # لا يرمي أبداً
```
اختبار فعلي على `requirements.txt` من `sl-rwl/test_1` (6 حزم قديمة عمداً) — كل
حزمة رجّعت ثغرات حقيقية من OSV.dev، مثال: `django==2.2.0` → `GHSA-2gwj-...` +
٦٦ معرّفاً آخر (انظر بند ٢).

### `backend/tools/secret_tools.py`
```python
def scan_secrets(code_files: dict[str, str]) -> list[dict]: ...
```
اختبار فعلي مزدوج: `app.py` الحقيقي من `sl-rwl/test_1` → لا كشف (نظيف فعلاً)،
وملف محلي بمفاتيح وهمية بكل الأنماط الخمسة (GitHub/OpenAI/AWS/Google/عام) →
**8/8** اكتُشفت بالنوع الصحيح والتقنيع الصحيح، بلا أي إشارة كاذبة.

---

## ٢. تعديل على العقود — `check_vulnerabilities`

**قبل:** `{"package", "version", "vuln_ids", "summary"}` — كل المعرّفات.
**بعد:**
```python
{"package": str, "version": str, "vuln_ids": list[str], "total_count": int, "summary": str}
```
`vuln_ids` محدودة بأول **5** معرّفات، `total_count` هو العدد الحقيقي، و`summary`
أصبح ملخص أول ثغرة فقط بدل دمج كل الملخصات.

**السبب:** `django==2.2.0` وحده رجّع **71** معرّف ثغرة. تمرير هذا الحجم لكل حزمة
قديمة عبر `findings` إلى الـ LLM في node التقرير يُضخّم الـ state والتكلفة بلا
فائدة إضافية — 5 أمثلة + عدد كلي كافٍ كدليل. مُحدَّث في `CONTRACTS.md`.

---

## ٣. تنبيه — استثناءات `fetch_repo_data` غير `RepoNotFound`

الدالة تستخدم `resp.raise_for_status()` داخلياً، فقد ترمي `requests.HTTPError`
عاماً في حالات غير `RepoNotFound` (404 فقط): **403** عند تجاوز حد استعلامات
GitHub، أو **500/502** عند عطل مؤقت في GitHub نفسه. تحقّقتُ من `fetch.py` —
`fetch_node` يمسكها بالفعل عبر `except Exception` عام بعد `except RepoNotFound`
(رسالة `tool_error` منفصلة عن `not_found`)، فلا حاجة لتعديل حالياً. **فقط
تنبيه لأي تعديل مستقبلي على node الجلب:** لا يُضيَّق هذا الـ catch إلى
`RepoNotFound` وحدها، وإلا ستُسقِط هذه الحالات الـ graph بدل رسالة مفهومة.

---

## ٤. قاعدة الكتابة (بعد حادثة Flask)

**`open_issue` لا تُستدعى إلا على مستودعات نملكها (`sl-rwl/*`).** أي مستودع
خارجي = قراءة فقط عبر `fetch_repo_data`، أبداً كتابة. السبب: سكربت اختبار
استخدم مستودع Flask الحقيقي كسيناريو "نجاح" مع موافقة تلقائية ففتح بلاغاً
فعلياً هناك (أُغلق لاحقاً من قِبل قائمي المشروع، لا يمكن حذفه). أي كود أو
سكربت اختبار يستدعي `open_issue` أو يُشغّل الـ graph حتى `publish` مع
`approved=True` يجب أن يستهدف `sl-rwl/*` حصراً، أو يحاكي الاستدعاء (mock).

---

## ٥. ملف الاختبار المحلي غير المرفوع

`scripts/fixtures/fake_secrets_sample.py` يحتوي مفاتيح وهمية بصيغ حقيقية
(لإثبات أن `scan_secrets` يكتشف شيئاً، لأن `app.py` الحقيقي نظيف). **غير مرفوع
لـ git** (مُضاف لـ `.gitignore`) لأن صيغه تطابق ما يبحث عنه GitHub push
protection حرفياً — رفعه قد يُحظر. لإعادة إنشائه محلياً:
```bash
python scripts/generate_fake_secrets_fixture.py
```
السكربت نفسه آمن للرفع: كل مفتاح مبني من (بادئة + جسم) في سطرين منفصلين،
فلا يوجد سطر واحد فيه يطابق نمط سرّ كامل.

---

## ٦. ما تبقّى من المسار الثاني

- الـ prompts (تعليمات الوكلاء الثلاثة + التقرير + قواعد اللغة والحواجز)
- الوكلاء الثلاثة `backend/graph/agents.py` (`security_agent`, `issues_agent`, `docs_agent`)
- node التقرير `backend/graph/report.py` (`report_node`)
- واجهة Streamlit + مبدل اللغة + أزرار الموافقة/الرفض
- الاختبارات الرسمية (pytest) + إثبات التنفيذ
