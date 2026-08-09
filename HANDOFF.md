# تسليم المسار الأول → المسار الثاني

> الـ graph مبنيّ ومختبَر كاملاً ويعمل الآن على stubs. هذه الوثيقة تقول لك
> بالضبط ما الذي تبنيه وأين، حتى ينزل كودك مكان الـ stubs بلا تعديل سطر واحد
> في الـ graph.

---

## ١. تعديلات على العقود — إضافية، لا تكسر شيئاً عندك

أُضيفت أربعة حقول لـ `AgentState`. **كل الحقول القديمة كما هي**، فما بنيتَه
على العقد الأصلي يبقى صالحاً.

| الحقل | النوع | من يكتبه | لماذا أُضيف |
|---|---|---|---|
| `issue_title` | `str` | **node التقرير (أنت)** | `/approve` يحتاج عنواناً ليفتح به البلاغ |
| `issue_body` | `str` | **node التقرير (أنت)** | ونصاً ليكتبه فيه |
| `approved` | `Optional[bool]` | الـ backend عند الاستئناف | `None`=لم يُسأل، `True`=وافق، `False`=رفض |
| `supervisor_log` | `Annotated[list[str], operator.add]` | كل node | أثر القرارات — البريف يطلب إظهار التتبّع في الديمو |

**السبب:** بدون `issue_title` و `issue_body` لا يعرف `/approve` ماذا يفتح.
كان الخيار البديل استخراجهما من نص التقرير داخل الـ graph، وهو هشّ ويكسر عند
تغيّر صياغة التقرير.

**ما يلزمك عملياً:** `report_node` يرجع ثلاثة مفاتيح بدل واحد:
```python
return {"report": ..., "issue_title": ..., "issue_body": ...}
```

---

## ٢. مزوّد الـ LLM — محسوم

لا تستورد مزوّداً بعينه. نادِ المصنع:

```python
from backend.llm import get_llm

llm = get_llm(temperature=0)          # chat model جاهز
llm = get_llm().with_structured_output(MyModel)   # مخرَج منظَّم
```

المزوّد يُضبط من `LLM_PROVIDER` في `.env` (الافتراضي `openai`، الموديل
`gpt-4o-mini`). المتاح: `openai` | `openrouter` | `anthropic` | `google`.
التبديل = سطر واحد في `.env` + إلغاء تعليق سطر في `requirements.txt`، بلا لمس
أي كود.

قبل أي تشخيص للـ graph، تأكّد من المفتاح وحده:
```bash
python scripts/check_llm.py
```
يكشف أشهر خطأ: مفتاح من مزوّد موجَّه لخادم مزوّد آخر (مفاتيح OpenRouter تبدأ
بـ `sk-or-v1` وترفضها OpenAI بـ 401).

---

## ٣. الملفات التي تبنيها — والتواقيع التي يستوردها الـ graph

الـ graph يستورد هذه الأسماء بالضبط. أي اختلاف في الاسم أو المسار = كسر الربط.

### `backend/tools/github_tools.py`
```python
def parse_repo_url(url: str) -> tuple[str, str] | None: ...
def fetch_repo_data(owner: str, repo: str) -> dict: ...
def open_issue(owner: str, repo: str, title: str, body: str) -> str: ...
class RepoNotFound(Exception): ...
class MissingToken(Exception): ...
```

### `backend/tools/osv_tools.py` و `backend/tools/secret_tools.py`
كما في `CONTRACTS.md` بلا تغيير — الـ graph لا يستوردهما مباشرة، وكلاء الأمن
عندك هم من ينادونهما.

### `backend/graph/agents.py`
ثلاث دوال، كل واحدة تأخذ الـ state وترجع dict:
```python
def security_agent(state: AgentState) -> dict:
    return {"findings": [...], "agents_done": ["security"]}

def issues_agent(state: AgentState) -> dict:
    return {"findings": [...], "agents_done": ["issues"]}

def docs_agent(state: AgentState) -> dict:
    return {"findings": [...], "agents_done": ["docs"]}
```

> **حرج:** كل وكيل **يجب** أن يرجع `agents_done` باسمه. الحقل تراكمي
> (`operator.add`) فلا تُرجع القائمة كاملة — عنصراً واحداً فقط. لو نسيتَه،
> يظنّ المشرف أن الوكيل لم يعمل ويعيده. (حزام أمان في المشرف يوقف الحلقة بعد
> ٥ دورات، لكنه علاج للعرَض لا للسبب.)

### `backend/graph/report.py`
```python
def report_node(state: AgentState) -> dict:
    return {"report": ..., "issue_title": ..., "issue_body": ...}
```
اقرأ `state["findings"]` (متراكمة من كل الوكلاء) و `state["language"]`
(`"en"` أو `"ar"`) واكتب التقرير بلغة المستخدم.

---

## ٤. ما الذي يصل إليك في الـ state

عند تشغيل وكيلك تكون هذه الحقول جاهزة ومضمونة:

- `repo_data` — كامل بشكل العقد، **ولن يكون فارغاً**: node الجلب يوقف المسار
  قبلك لو رجع المستودع بلا محتوى.
- `owner` / `repo` — منظَّفان ومُتحقَّق منهما.
- `language` — `"en"` أو `"ar"` فقط، لا قيمة ثالثة.
- `findings` — ما تراكم من الوكلاء السابقين (قد تكون فارغة لو كنت الأول).
- `agents_done` — من عمل قبلك.

**لن يصل إليك المستودع غير الموجود ولا الرابط غير الصالح** — الحارس والجلب
يوقفانهما قبل المشرف أصلاً.

---

## ٥. المشرف قد لا يشغّل وكيلك — وهذا مقصود

المشرف يحسب "الأهلية" قبل أن يقرر:

| الوكيل | لا يُشغَّل إذا |
|---|---|
| `security` | لا ملفات تبعيات **ولا** ملفات كود |
| `issues` | لا بلاغات مفتوحة |
| `docs` | — مؤهَّل دائماً (غياب README نفسه ملاحظة) |

فوق الأهلية، الـ LLM يختار الترتيب وقد يتوقف مبكراً. لذلك **لا تفترض في
`report_node` أن الوكلاء الثلاثة عملوا** — اقرأ `agents_done` واكتب التقرير على
ما وُجد فعلاً.

---

## ٦. قائمة حذف الـ stubs (نقطة الالتقاء الأولى)

البريف يمنع صراحةً أي أداة ترجع بيانات معلّبة. عند اكتمال كودك نحذف:

1. `backend/stubs.py` — الملف كاملاً
2. كتلة `try/except ImportError` في `backend/graph/guardrail.py`
3. كتلة `try/except ImportError` في `backend/graph/fetch.py`
4. كتلتَي `try/except ImportError` في `backend/graph/build.py`

كل كتلة معلَّمة بـ `# ── مؤقت: يُحذف عند نقطة الالتقاء الأولى ──`.
بعد الحذف تبقى `from ... import ...` المباشرة فقط.

للتأكد من عدم بقاء شيء:
```bash
grep -rn "stubs" backend/ && echo "بقي شيء!" || echo "نظيف"
```

---

## ٧. تشغيل ما بُني حتى الآن

```bash
pip install -r requirements.txt
python scripts/smoke_graph.py        # ٦ سيناريوهات: سليم، فشل، رفض، موافقة/رفض نشر
python scripts/smoke_supervisor.py   # ١١ فحصاً لمنطق المشرف
```
كلاهما يعمل بلا مفتاح LLM وبلا شبكة (المشرف يسقط على ترتيبه الحتمي).

---

## ٨. ما تبقّى مشتركاً

الـ backend (FastAPI) لم يُبنَ بعد — هو عمل مشترك في نقطة الالتقاء الثانية
حسب `WORK_SPLIT.md`. الـ graph جاهز له: `build_graph()` يرجع graph مُصرَّفاً
بـ `MemorySaver` ومتوقفاً قبل `publish`، فالـ `/analyze` ينادي `invoke` ويقرأ
التقرير، و`/approve` ينادي `update_state(config, {"approved": ...})` ثم
`invoke(None, config)`.
