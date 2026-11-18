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
4. **نظافة التراخيص والأمان (License & Supply Chain Safety):** يُسمح في اعتماديات التشغيل فقط بالمكتبات ذات التراخيص المفتوحة القياسية (`MIT`, `Apache-2.0`, `BSD-3-Clause`). يُمنع استخدام أي مكتبات غير رسمية لتجاوز الحماية أو تراخيص مقيدة. **استثناء تطوير/اختبار محدود:** يُسمح بمكتبة `Pygments` وحدها بترخيص `BSD-2-Clause` داخل `requirements-dev.txt` فقط؛ ولا يُسمح بهذا الترخيص في `requirements.txt` أو اعتماديات التشغيل. يظل استثناء Dependency Review محصوراً في الحزمة `pkg:pypi/pygments`.
5. **بوابة الجودة والاختبار (No Untested Merges):** لا يُعد أي كود مكتملاً إلا باجتياز اختبارات `pytest` وفحص التراخيص تلقائياً عبر GitHub Actions.

---

## 1.1 الذاكرة واستمرارية الحالة (Encrypted State Persistence)

- تُحفظ جلسات SQLite بين تشغيلات GitHub Actions عبر الفرع المنفصل `engine-state` باستخدام `scripts/sync_state.py restore|save`.
- يجب ضبط `ENGINE_STATE_ENCRYPTION_KEY` كسِرّ GitHub بطول لا يقل عن 32 بايت، مع صلاحية `contents: write` للـ workflow الذي ينفذ الحفظ. لا تُكتب المفاتيح في المستودع أو السجلات.
- تُشفّر لقطة SQLite محلياً قبل رفعها (AES-256-CBC مع HMAC للتحقق من سلامة البيانات). لا يُرفع ملف قاعدة البيانات بصورته الصريحة.
- يجب تنفيذ `restore` قبل تشغيل الوكلاء و`save` بعد اكتمال المهمة، مع عدم تفعيل حفظ متزامن على الفرع نفسه من أكثر من تشغيل.
- الفهرسة الافتراضية تستخدم تضمين CPU محلياً بلا تنزيل نموذج أو اعتماديات ثنائية. يمكن تفعيل ONNX فقط عند توفير نموذج ومجزئ محليين بعد فحص تراخيص كل الاعتماديات. لم يُعتمد FAISS حالياً لأن عجلات NumPy الثنائية التي فُحصت تضم مكوّناً بترخيص LGPL خارج قائمة تراخيص التشغيل.

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
│   ├── database.py                 # SQLite WAL للذاكرة والمعرفة ونقاط استئناف المسارات
│   ├── embeddings.py               # تضمين CPU حتمي بلا تنزيلات؛ ONNX محلي اختياري بعد تدقيق الاعتمادات
│   ├── semantic_cache.py           # كاش دلالي مع فهرسة cosine CPU؛ FAISS مؤجل لحين اجتياز تدقيق التراخيص الثنائية
│   ├── knowledge_store.py          # مخزن معرفة واسترجاع دلالي محلي
│   └── state_store.py              # نسخ SQLite مشفرة واستعادتها من فرع GitHub مخصص
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

---

## 1.2 المرحلة الثالثة — Orchestrator & GitHub Actions Runner

### Provider Orchestrator
- `core/provider_orchestrator.py` يكتشف محرك GGUF المحلي إذا كان النموذج و`llama-cpp-python` متاحين، ويقرأ بوابات OpenAI-compatible الاختيارية من متغير `ENGINE_PUBLIC_PROVIDERS` بصيغة JSON.
- تُفحص صحة كل بوابة عبر `GET /models`، ثم يُرتب المزودون وفق الصحة وموثوقية النجاح ومتوسط زمن الاستجابة المسجل في SQLite.
- عند الفشل ينتقل المحرك إلى المزود التالي مرة واحدة فقط في الدورة نفسها؛ لا يعيد الطلب إلى المزود ذاته. `request_id` يمنع تكرار النتيجة عند إعادة تشغيل المهمة، ويرفض استخدام المفتاح نفسه مع Prompt مختلف.
- لا توجد بوابة عامة افتراضية مفترضة أو مضمونة المجانية/التوافر. لا يتم إرسال بيانات المهام إلى طرف ثالث إلا إذا أضاف المشغل عنوانه صراحة إلى `ENGINE_PUBLIC_PROVIDERS`. يجب التحقق من شروط الاستخدام والخصوصية وحدود الاستخدام لكل بوابة قبل إضافتها.
- مثال إعداد (دون مفتاح إلزامي؛ `token_env` اختياري):
  ```json
  [
    {"name":"approved-gateway","base_url":"https://gateway.example/v1","model":"model-id"}
  ]
  ```
  لا تستخدم المثال كعنوان فعلي؛ استبدله بعنوان بوابة تم التحقق منها.

### Agent tool execution
- `AgentFactory` يستخدم `ProviderOrchestrator` تلقائياً ما لم يتم حقن Executor مخصص.
- يستطيع النموذج طلب أدوات مسجلة بصيغة JSON، لكن التنفيذ يقتصر على الأدوات الممنوحة صراحة للوكيل، وبحد أقصى أربعة استدعاءات في الدورة. نتائج الأدوات تعامل كبيانات غير موثوقة عند بناء طلب المتابعة.

### Web and repository tools
- `tools/web_research.py` يستخدم مكتبات Python القياسية للبحث عبر HTML DuckDuckGo وتنظيف HTML إلى Markdown. يرفض عناوين الشبكات المحلية وعناوين IP غير العامة، ويعيد فحص الوجهة النهائية بعد التحويل.
- `tools/repo_tools.py` يوفّر قراءة Issues، التعليق وإغلاق Issue، إنشاء الفروع، ورفع ملفات ذاكرة عبر GitHub REST API ضمن المستودع المحدد.

### Engine runner
- `.github/workflows/engine_runner.yml` يستقبل Issues المفتوحة/المعدلة التي يبدأ عنوانها بـ `[TASK]`، و`workflow_dispatch`، وجدولة صيانة كل ست ساعات.
- يعلّق بنتيجة المهمة ويغلق Issue بعد نجاح التنفيذ فقط. فشل التنفيذ يبقي Issue مفتوحاً.
- يستخدم Cache لحفظ نموذج GGUF موجود مسبقاً؛ الـ Cache لا ينزّل النموذج ولا ينشئه. يجب توفير النموذج ومراجعة مصدره وترخيصه قبل التشغيل. لا يوجد ضمان عام بأن الإقلاع أقل من 30 ثانية.
- استمرارية الحالة المشفرة تعمل فقط عند ضبط `ENGINE_STATE_ENCRYPTION_KEY` كسِرّ GitHub (32 بايت على الأقل)؛ عند غيابه يتخطى الـ Runner الاستعادة والحفظ بأمان. لا يُشتق مفتاح تشفير من `GITHUB_TOKEN` أو `repository_id`، ولا تُرفع قاعدة بيانات صريحة كـ Artifact. يلزم إعداد السر مرة واحدة لتفعيل الاستمرارية المشفرة.
- يمنع `concurrency` تداخل تشغيلات Runner على فرع الحالة. يجب ألا يُستخدم هذا الفرع لكتابة متزامنة من workflows أخرى.

### حدود التشغيل الحالية
- لا يوجد مزود استدلال خارجي تلقائي مضمون دون إعداد. إذا لم يوجد نموذج محلي صالح أو بوابة معتمدة في `ENGINE_PUBLIC_PROVIDERS`، يفشل طلب المهمة برسالة واضحة بدلاً من ادعاء إتمامه.
- Actions بيئة مؤقتة وليست خدمة دائمة؛ الجدولة كل ست ساعات ليست ضمان تشغيل دائم أو تنفيذ فوري خارج حدود GitHub Actions.
- لم تُضف اعتماديات Runtime جديدة؛ الأدوات أعلاه مبنية على Python Standard Library. تظل بوابات Dependency Review وRuntime/Development License Allowlist إلزامية قبل الدمج.
