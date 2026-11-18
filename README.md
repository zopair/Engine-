# ENGINE — 100% GitHub-Native Autonomous Intelligence Platform (`zopair/Engine-`)

> **⚠️ تنبيه ملزم لوكلاء البرمجة والمطورين (Strict Architectural Contract):**
> هذا المستند هو **المرجع الهندسي الوحيد المعتمد (Single Source of Truth)** للمشروع. يعمل هذا المحرك **بالكامل داخل بنية GitHub (GitHub Actions + GitHub API + GitHub Pages)** بدون أي استضافات خارجية (لا Hugging Face، لا Render، لا خوادم خارجية مدفوعة). يُمنع الخروج عن هذه المعمارية أو إضافة اعتماديات ثقيلة.

---

## 1. الرؤية والهدف الهندسي (GitHub-Native Mandate)
**ENGINE** هو منصة ذكاء اصطناعي سيادية مستقلة، تعمل مباشرة داخل مستودعات GitHub كـ **محرك تنفيذ سحابي مؤقت (Ephemeral GitHub Actions Execution Fabric)**، لإنتاج وإدارة وتشغيل الوكلاء الذكيين ومسارات العمل والأدوات، مع قدرة على التطور الذاتي المحكوم وتحديث حالته وذاكرته داخل المستودع نفسه.

### القواعد الحاكمة غير القابلة للتفاوض (Hard Constraints):
1. **بيئة التشغيل الحصرية هي GitHub (100% GitHub-Native):**
   - **المحرك والوكلاء:** يعملان عبر **GitHub Actions Workflows** (عبر `workflow_dispatch` أو `schedule` أو `repository_dispatch` أو `issues` كواجهة أوامر).
   - **الواجهة ولوحة التحكم (اختياري):** ملفات ويب ساكنة (`HTML/Vanilla JS`) تعمل مباشرة عبر **GitHub Pages** وتتصل بالمحرك عبر GitHub REST API.
   - **إلغاء الاستضافات الخارجية:** لا حاجة لـ Hugging Face Spaces أو خوادم خارجية دائمة.
2. **ميزانية صفرية (Zero-Cost Operation):** تكلفة التشغيل تساوي `0$`. الاعتماد الكلي على الدقائق المجانية في GitHub Actions للمستودعات العامة والمصادر المفتوحة المجانية.
3. **السرعة القصوى في الإقلاع (Fast Ephemeral Boot):** لأن مهام GitHub Actions تبدأ وتنتهي في دقائق، يجب أن يكون وقت تثبيت المكتبات وتشغيل المحرك أقل من **45 ثانية** (يُمنع تحميل نماذج ضخمة بـ 5 جيجابايت في كل تشغيل؛ نستخدم نماذج فائقة الصغر مثل `Qwen2.5-0.5B` أو `1.5B` بصيغة `GGUF Q4_K_M` مع تفعيل `actions/cache` لحفظها بين الجلسات).
4. **نظافة التراخيص والأمان (License & Supply Chain Safety):** يُسمح فقط بالمكتبات ذات التراخيص المفتوحة القياسية (`MIT`, `Apache-2.0`, `BSD-3-Clause`). يُمنع استخدام أي مكتبات غير رسمية لتجاوز الحماية أو تراخيص مقيدة.
5. **بوابة الجودة والاختبار (No Untested Merges):** لا يُعد أي كود مكتملاً إلا باجتياز اختبارات `pytest` وفحص التراخيص تلقائياً عبر GitHub Actions.

---

## 2. المعمارية الهندسية المعتمدة (Modular GitHub-Native Architecture)

```text
zopair/Engine-/
├── .github/
│   └── workflows/
│       ├── engine_runner.yml       # المحرك الرئيسي: يستقبل الأوامر (Dispatch/Issues/Cron) ويشغل الوكلاء
│       ├── self_evolution.yml      # دورة التطور الذاتي المجدولة (توليد تحسينات في فرع معزول)
│       └── ci.yml                  # بوابة الاختبار التلقائي وفحص التراخيص والأمان (pytest)
├── core/
│   ├── __init__.py
│   ├── config.py                   # الإعدادات المركزية وحدود الموارد (GitHub Runner: 4 CPU / 16GB RAM)
│   ├── local_engine.py             # نواة الاستدلال السريعة (llama-cpp-python + نماذج GGUF مخزنة في GitHub Cache)
│   ├── provider_orchestrator.py    # طبقة التجريد وتدوير المصادر المفتوحة/المجانية والـ Fallback التلقائي
│   └── resource_optimizer.py       # مراقبة استهلاك الموارد وتسريع الإقلاع المؤقت (Ephemeral Optimization)
├── memory/
│   ├── __init__.py
│   ├── database.py                 # قاعدة بيانات SQLite خفيفة تُحفظ وتُحدّث كـ Artifact أو داخل فرع البيانات
│   ├── semantic_cache.py           # الكاش الدلالي السريع (FAISS-CPU + ONNX Embeddings)
│   └── knowledge_store.py          # استرجاع المعرفة والسياق من ملفات المستودع (JSON/Markdown)
├── factories/
│   ├── __init__.py
│   ├── agent_factory.py            # إنشاء وتكوين واختبار الوكلاء الذكيين ديناميكياً
│   └── workflow_factory.py         # بناء مسارات عمل قابلة للاستئناف عبر الجلسات (State Persistence)
├── tools/
│   ├── __init__.py
│   ├── web_research.py             # البحث وتنظيف الصفحات إلى Markdown (Crawl4AI / DuckDuckGo)
│   └── repo_tools.py               # أدوات التفاعل الذاتي مع GitHub API (فروع، PRs، Issues، Artifacts)
├── evolution/
│   ├── __init__.py
│   └── self_evolution.py           # دورة التطوير الذاتي المحكومة (توليد في فرع معزول -> اختبار -> PR)
├── docs/                           # واجهة تحكم ويب ساكنة (HTML/CSS/JS) تعمل مباشرة على GitHub Pages
│   └── index.html
├── tests/
│   ├── test_core.py                # اختبارات النواة والذاكرة والكاش
│   └── test_factories.py           # اختبارات مصانع الوكلاء ومسارات العمل
├── cli.py                          # نقطة الدخول الموحدة لتشغيل المحرك من سطر الأوامر داخل GitHub Actions
├── requirements.txt                # اعتماديات CPU فائقة الخفة وسريعة التثبيت
└── README.md                       # الدستور المعماري المرجعي (هذا الملف)
```