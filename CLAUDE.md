# CLAUDE.md

## وصف المشروع باختصار

**GitHub Repo Health Agent** — نظام وكلاء متعدد (multi-agent) مبني على LangGraph يفحص مستودع GitHub شاملاً: الأمان (ثغرات الاعتماديات عبر OSV.dev + مفاتيح مكشوفة في الكود)، البلاغات المفتوحة (تكرار، إهمال، أولويات)، والتوثيق (README مقابل معايير محددة). يُشرف على تسلسل العمل node مشرف (Supervisor) يقرر ديناميكياً أي وكيل يعمل تالياً. يُصدر النظام تقريراً بلغة المستخدم (عربي/إنجليزي) ويتوقف بانتظار **موافقة بشرية صريحة (human-in-the-loop)** قبل فتح أي بلاغ (issue) فعلي في المستودع. التفاصيل الكاملة للفكرة والمشكلة والحل في [PROJECT_IDEA.md](PROJECT_IDEA.md).

المشروع مقسّم لمسارين متوازيين (انظر [WORK_SPLIT.md](WORK_SPLIT.md)):
- **المسار الأول**: هيكل الـ Graph، الـ State، الحارس، الجلب، المشرف، المسارات الشرطية.
- **المسار الثاني**: الأدوات (GitHub/OSV/فحص المفاتيح)، الـ prompts، الوكلاء الثلاثة (أمن/بلاغات/توثيق)، node التقرير، واجهة Streamlit، الاختبارات.

## المتطلبات الإلزامية من البريف

كل بند هنا إلزامي — غيابه يخصم درجات حتى لو كان العرض جيداً:

- نظام **LangGraph** كامل: State مُنمّط (typed)، عقدتان (nodes) على الأقل، وحافة شرطية واحدة على الأقل تُغيّر المسار فعلياً.
- **3 أدوات على الأقل**، واحدة منها تلامس نظاماً خارجياً حقيقياً (API/قاعدة بيانات/vector store). **ممنوع أي أداة وهمية (stub) ترجع بيانات معلّبة في النسخة النهائية.**
- **Guardrails**: برومبتات تحافظ على الشخصية وترفض الطلبات خارج النطاق.
- **واجهة مستخدم** (Streamlit أو غيرها) تتواصل مع الـ backend عبر HTTP فقط — **يُمنع أن تُشغّل الواجهة الـ graph مباشرة**.
- **اختبارات** مع إثبات تنفيذ (لقطة شاشة/مخرجات طرفية)، تغطي مسار نجاح واحد ومسار فشل واحد على الأقل.
- **عنصر متقدم واحد على الأقل**: هذا المشروع يستخدم **human-in-the-loop interrupts** (التوقف قبل فتح الـ issue).
- **README** يسمح لأي غريب بتشغيل المشروع من الصفر (المتطلبات المسبقة، متغيرات البيئة ومصادرها، خطوات التثبيت والتشغيل، مثال استعلام مع مخرجه، القيود المعروفة).
- **عرض حي**: مسار نجاح كامل + طلب فاشل/خارج النطاق يُظهر رفض الوكيل بدل اختلاق إجابة.
- **موعد التسليم**: الخميس 13 أغسطس 2026، ملف .zip واحد (كود + README + سلايدات PDF) بالإيميل للمشرف، عرض 10 دقائق كحد أقصى شاملاً الديمو الحي.

## ملخص العقود (المرجع الكامل: [CONTRACTS.md](CONTRACTS.md))

### الـ State (`backend/state.py`)
- إدخال: `repo_url`, `language`.
- يملؤها الحارس: `owner`, `repo`, `rejection_reason`.
- تُكتب مرة واحدة: `repo_data` (meta/readme/open_issues/dependency_files/code_files).
- يقررها المشرف: `next_agent`.
- تتراكم عبر `Annotated + operator.add`: `agents_done`, `findings` (كل `finding` = agent/severity/title/detail/evidence).
- مخرجات نهائية: `report`, `issue_url`.
- **حقول إضافية (من `HANDOFF.md`، لا تكسر العقد الأصلي)**:
  - `issue_title: str`, `issue_body: str` — يكتبهما `report_node` ليستخدمهما `/approve` عند فتح البلاغ.
  - `approved: Optional[bool]` — يكتبه الـ backend عند الاستئناف (`None`=لم يُسأل، `True`=وافق، `False`=رفض).
  - `supervisor_log: Annotated[list[str], operator.add]` — أثر قرارات كل node، تراكمي، يُظهر في الديمو.

### تواقيع الأدوات (كل دالة مستقلة، تُختبر بدون الـ graph)
- `backend/tools/github_tools.py`: `parse_repo_url(url) -> (owner, repo) | None`، `fetch_repo_data(owner, repo) -> dict` (يرمي `RepoNotFound`)، `open_issue(owner, repo, title, body) -> str` (يرمي `MissingToken`).
- `backend/tools/osv_tools.py`: `parse_requirements(text) -> list[tuple[str, str]]`، `check_vulnerabilities(requirements_text, limit=10) -> list[dict]` (لا يرمي استثناءً — الأخطاء تُسجَّل داخل النتائج).
- `backend/tools/secret_tools.py`: `scan_secrets(code_files) -> list[dict]` (file/line/kind/snippet مقنَّع جزئياً).

### الوكلاء الثلاثة (`backend/graph/agents.py`)
- كل وكيل دالة تأخذ `state: AgentState` وترجع `dict`: `security_agent`, `issues_agent`, `docs_agent`.
- **حرج**: كل وكيل **يجب** أن يرجع `agents_done` بعنصر واحد فقط باسمه (مثلاً `{"agents_done": ["security"]}`) — الحقل تراكمي (`operator.add`)، فإرجاع القائمة كاملة أو نسيان الحقل يجعل المشرف يظن أن الوكيل لم يعمل ويعيد تشغيله (حزام أمان في المشرف يوقف الحلقة بعد 5 دورات كعلاج للعرَض لا للسبب).
- المشرف قد لا يشغّل وكيلاً معيناً حسب أهليته (مثلاً `security` لا يعمل بلا ملفات تبعيات ولا ملفات كود) — لا تفترض داخل `report_node` أن الوكلاء الثلاثة عملوا جميعاً، اقرأ `agents_done` واكتب على ما وُجد فعلاً.

### node التقرير (`backend/graph/report.py`)
- `report_node(state) -> dict` يرجع **ثلاثة مفاتيح** لا مفتاحاً واحداً: `{"report": ..., "issue_title": ..., "issue_body": ...}`.
- يقرأ `state["findings"]` المتراكمة و`state["language"]` (`"en"` أو `"ar"` فقط) ويكتب التقرير بلغة المستخدم.

### مزوّد الـ LLM (`backend/llm.py`)
- **لا يُستورد مزوّد بعينه مباشرة في أي كود وكيل أو node.** يُنادى المصنع فقط:
  ```python
  from backend.llm import get_llm
  llm = get_llm(temperature=0)
  llm = get_llm().with_structured_output(MyModel)
  ```
- المزوّد يُضبط عبر `LLM_PROVIDER` في `.env` (الافتراضي `openai`، الموديل `gpt-4o-mini`). المتاح: `openai` | `openrouter` | `anthropic` | `google`. التبديل = سطر واحد في `.env` بلا لمس الكود.
- للتحقق من المفتاح قبل أي تشخيص للـ graph: `python scripts/check_llm.py`.

### عقد الـ API
- `POST /analyze`: طلب `{repo_url, language}` → رد `{thread_id, status: awaiting_approval|rejected, report, agents_done}`.
- `POST /approve`: طلب `{thread_id, approved}` → رد `{status: done|cancelled, issue_url}`.
- `GET /health`: `{status: "ok"}`.

## قواعد العمل

- **تحدث معي بالعربية دائماً.** المصطلحات التقنية، الكود، وتعليقات الكود تبقى بالإنجليزية.
- **لا تعدّل ملفات المسار الأول** (`state.py`، الحارس، الجلب، المشرف، المسارات الشرطية والحلقة) — العمل مقسّم بفصل الملفات لتفادي التعارضات؛ أي تعديل هناك يتطلب تنسيقاً مسبقاً.
- **اتبع تواقيع العقود حرفياً** كما هي في [CONTRACTS.md](CONTRACTS.md) — أي تغيير في اسم دالة، مدخلاتها، أو شكل مخرجاتها يُبلَّغ فوراً قبل التنفيذ، لا يُفترض بصمت.
- **لا ترفع `.env` أبداً** إلى git تحت أي ظرف (وهو مُدرَج بالفعل في `.gitignore`).
- **لا تنفّذ `git push` أو تفتح Pull Request أو تعدّل فرع `main` إلا بطلب صريح مني.**
