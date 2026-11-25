# وثيقة تحليل المتطلبات البرمجية والتقنية (SRS)

**المشروع:** المنصة الرقمية للتواصل المجتمعي – لجنة أولياء أمور الطلاب (مدرسة المحجر الابتدائية)

**الإصدار:** 1.0 (نسخة منقحة ومعتمدة بناءً على مدخلات أصحاب المصلحة)

**التاريخ:** 24 نوفمبر 2026

---

## 1. المقدمة (Introduction)

تُعد هذه المنصة تطبيق ويب متجاوب (Responsive Web Application) مصمم وفق منهجية "الهاتف أولاً" (Mobile-First) مع توافق كامل مع أجهزة الحاسوب، ليكون قناة التواصل الرسمية والمركزية بين **لجنة أولياء أمور الطلاب في مدرسة المحجر الابتدائية** وأهالي الطلاب. تتيح المنصة للجنة التعريف بأعضائها وأدوارهم، ونشر الإعلانات والفعاليات والأنشطة المدرسية (مدعومة بالنصوص، الصور، وروابط الوسائط الخارجية بمختلف أنواعها مثل مقاطع الفيديو، الريلز ومنشورات وسائل التواصل الاجتماعي، الصور الخارجية، والملفات الصوتية)، بالإضافة إلى توفير آليات تفاعلية منظمة تُمكّن الأهالي من إبداء آرائهم، طرح المقترحات والمشكلات العامة، والتسجيل للمشاركة في الفعاليات عبر تكامل مباشر ومُضمّن مع نماذج Google Forms.

---

## 2. الغرض من الوثيقة (Purpose)

تهدف هذه الوثيقة إلى تقديم مرجع تقني ووظيفي رسمي ودقيق يحدد جميع متطلبات النظام، حدوده، قيوده، ومعايير قبوله، وذلك لخدمة الفئات التالية:

* **فريق التطوير والهندسة البرمجية:** لتحديد البنية التقنية، واجهات الاستخدام، تدفق البيانات، ومتطلبات الأداء والأمان أثناء التنفيذ.
* **أعضاء لجنة أولياء أمور الطلاب (العميل/إدارة النظام):** لتوثيق الصلاحيات الإدارية، آليات نشر المحتوى، وإدارة التفاعل مع الأهالي.
* **أصحاب المصلحة (إدارة المدرسة والأهالي):** لضمان وضوح الرؤية وتطابق المخرجات النهائية مع احتياجات المجتمع المدرسي وسهولة الوصول عبر الروابط المباشرة دون تعقيدات تقنية.

---

## 3. نطاق المشروع والمخرجات (Scope)

### 3.1 حدود المشروع (In-Scope)

* تطوير واجهة ويب متجاوبة باللغة العربية (RTL) تعمل بسلاسة على متصفحات الهواتف الذكية (iOS/Android) والحواسيب عبر رابط مباشر (URL) دون الحاجة لتثبيت تطبيق من المتاجر.
* بناء لوحة تحكم مبسطة وآمنة لأعضاء اللجنة لإدارة المحتوى (إضافة/تعديل/حذف الأعضاء، الفعاليات، الإعلانات، وروابط النماذج).
* عرض دليل تعريفي لأعضاء لجنة أولياء الأمور يوضح الأسماء، الصفات الوظيفية/المهام داخل اللجنة، ووسائل التواصل المعتمدة.
* نظام نشر للإعلانات والفعاليات المدرسية يدعم النصوص المنسقة، الصور، وتضمين وربط أي نوع من الوسائط الخارجية مثل مقاطع الفيديو (YouTube، Vimeo، Dailymotion)، الريلز ومقاطع الفيديو القصيرة (Instagram Reels، Facebook Reels، TikTok، YouTube Shorts)، منشورات وسائل التواصل الاجتماعي (Instagram، Facebook، X، Threads، LinkedIn، Telegram)، روابط الصور والتصاميم والألبومات الخارجية (روابط الصور المباشرة الآمنة HTTPS، Google Photos، Canva)، والملفات الصوتية (SoundCloud، Spotify، Google Drive).
* تضمين نماذج تفاعلية مبنية عبر **Google Forms** داخل صفحات المنصة لاستقبال:
1. مقترحات وآراء الأهالي حول الشؤون المدرسية العامة.
2. طلبات المساعدة وطرح المشكلات العامة التي تواجه محيط المدرسة أو الطلاب.
3. استمارات التسجيل والمشاركة في الفعاليات والأنشطة المدرسية.


* نشر الكود البرمجي وتهيئته للعمل على بيئة استضافة سحابية مجانية (Free Tier Hosting).

### 3.2 خارج نطاق المشروع (Out-of-Scope)

* بناء نظام تسجيل دخول وحسابات شخصية فردية لكل ولي أمر (يتم الوصول للمحتوى والنماذج عبر الرابط العام لتقليل عوائق الاستخدام).
* تخزين ملفات الفيديو أو الصوت الخام مباشرة على خوادم الاستضافة (يُكتفى بتضمين وربط الروابط الخارجية للوسائط ومنصات التواصل الاجتماعي لتفادي استهلاك مساحة الاستضافة المجانية).
* الربط البرمجي المباشر مع أنظمة وزارة التربية والتعليم أو قواعد بيانات علامات وسجلات الطلاب الفردية.
* تطوير تطبيقات أصلية (Native Apps) لمتجري Apple App Store أو Google Play.

---

## 4. المتطلبات الوظيفية (Functional Requirements)

| المعرّف | الوحدة الوظيفية | الوصف التقني والتفصيلي للمتطلب |
| --- | --- | --- |
| **FR-01** | **عرض دليل أعضاء اللجنة** | يعرض النظام بطاقات تعريفية لأعضاء لجنة أولياء أمور الطلاب تتضمن: الاسم الكامل، الدور أو الوظيفة في اللجنة (رئيس، نائب، أمين صندوق، عضو، إلخ)، نبذة مختصرة عن المهام، وصورة اختيارية. |
| **FR-02** | **لوحة الإعلانات والفعاليات** | يتيح النظام عرض قائمة زمنية (من الأحدث للأقدم) للفعاليات، الأنشطة، والإعلانات المدرسية، مع إمكانية التصنيف (إعلان عام، فعالية قادمة، نشاط طلابي، مستجدات). |
| **FR-03** | **دعم الوسائط المتعددة** | يدعم النظام عرض الصور المضغوطة المحسّنة للويب، وتضمين وربط خمسة أنواع من الوسائط الخارجية (`video`، `reel`، `post`، `image`، `audio`) داخل تفاصيل الإعلان أو الفعالية عبر: (أ) مشغلات تضمين آمنة (`iframe` بالتحميل الكسول للمنصات المعتمدة مثل YouTube وVimeo وDailymotion وInstagram وFacebook وTikTok وSoundCloud وSpotify وGoogle Drive)، (ب) عرض الصور الخارجية الآمنة (`<img>` بالتحميل الكسول)، و(ج) بطاقات معاينة وروابط وصول خارجية آمنة للمنصات الاجتماعية التي لا تدعم التضمين المباشر بدون حالة (مثل X وThreads وLinkedIn وTelegram وGoogle Photos وCanva). |
| **FR-04** | **التفاعل عبر Google Forms** | يوفر النظام قسماً مخصصاً للتفاعل يضم نماذج Google Forms مُضمّنة (Embedded Iframes) أو روابط ذكية مُهيأة مسبقاً تشمل: (أ) نموذج إبداء الرأي والمقترحات العامة، (ب) نموذج الإبلاغ عن مشكلة عامة أو طلب مساعدة، (ج) نموذج التسجيل في فعالية محددة. |
| **FR-05** | **مشاركة المحتوى عبر WhatsApp** | يحتوي كل إعلان أو فعالية على زر مشاركة سريعة يولّد رابطاً مباشراً (Deep Link) مع عنوان الإعلان لتسهيل نشره في مجموعات الواتساب الخاصة بأهالي المدرسة. |
| **FR-06** | **لوحة إدارة المحتوى (Admin CMS)** | واجهة إدارية محمية بكلمة مرور/مصادقة تتيح لمسؤولي اللجنة إضافة وتعديل وحذف: بيانات الأعضاء، الإعلانات والفعاليات مع ربط روابط الوسائط الخارجية بجميع أنواعها مباشرة ضمن نموذج الإعلان (فيديو، رييل، منشور، صورة خارجية، صوت) مع التعرّف التلقائي على النوع دون إدخال يدوي له أو لعنوان فرعي، وروابط تضمين نماذج Google Forms دون الحاجة لتعديل الكود البرمجي. |

---

## 5. المتطلبات غير الوظيفية (Non-Functional Requirements)

### 5.1 الأداء وقابلية التوسع (Performance & Scalability)

* **مستوى التزامن (Concurrency):** يجب أن يتحمل النظام ما يصل إلى **500 مستخدم متزامن** (خاصة في أوقات الذروة فور إرسال رابط إعلان عاجل في مجموعات الأهالي) دون تدهور في الخدمة.
* **زمن الاستجابة (Response Time):** يجب ألا يتجاوز زمن استجابة الخادم (TTFB) واستعلامات البيانات **500 مللي ثانية (500ms)**، وأن يكتمل تحميل الصفحة الرئيسية على شبكات الجيل الرابع (4G) خلال أقل من ثانيتين.
* **تحسين الأصول (Asset Optimization):** ضغط الصور تلقائياً بصيغة WebP وتفعيل التحميل الكسول (Lazy Loading) للصور وإطارات الفيديو/النماذج المضمنة للحفاظ على باقة بيانات المستخدمين وتقليل استهلاك موارد الاستضافة.

### 5.2 سهولة الاستخدام وإمكانية الوصول (Usability & Accessibility)

* **تصميم Mobile-First:** تكيّف تلقائي كامل مع شاشات الهواتف الذكية بمختلف مقاساتها، مع أزرار لمس لا تقل أبعادها عن $44 \times 44$ بكسل.
* **دعم اللغة العربية (RTL):** التزام صارم باتجاه العرض من اليمين إلى اليسار (`dir="rtl"`) وخطوط عربية واضحة ومقروءة.
* **البساطة (Zero-Friction UX):** الوصول الفوري للمعلومات والنماذج بنقرتين كحد أقصى دون مطالبة ولي الأمر بإنشاء حساب أو تذكر كلمات مرور.

### 5.3 الأمان والخصوصية (Security & Privacy)

* **تشفير الاتصال:** إلزامية العمل عبر بروتوكول **HTTPS (SSL/TLS)** لحماية البيانات المنقولة.
* **حماية لوحة الإدارة:** تأمين مسارات التعديل والإدارة عبر مصادقة آمنة (مثل JWT أو NextAuth) لمنع أي وصول غير مصرح به لتغيير بيانات اللجنة أو روابط النماذج.
* **حماية المدخلات:** تعقيم جميع المدخلات النصية والروابط المضافة في لوحة الإدارة لمنع ثغرات حقن الأكواد (XSS)، وحصر تضمينات الإطارات (`iframe`) في نطاقات المنصات المعتمدة عبر التحقق الخلفي وسياسة أمان المحتوى (`CSP frame-src`)، واقتصار الصور الخارجية المباشرة على روابط HTTPS عامة وآمنة خالية من ملفات SVG أو ملفات الصوت والفيديو الخام.

### 5.4 التوافرية والصيانة (Availability & Maintainability)

* استهداف توافرية لا تقل عن **99.5%** ضمن حدود خطط الاستضافة المجانية، مع اعتماد بنية معيارية (Modular Architecture) تسهل إضافة أقسام أو نماذج جديدة مستقبلاً.

---

## 6. تحليل أصحاب المصلحة (Stakeholder Analysis)

| الفئة المستهدفة | الدور في المنظومة | الاهتمامات والأهداف الرئيسية |
| --- | --- | --- |
| **أهالي طلاب مدرسة المحجر الابتدائية** | المستخدمون النهائيون (End Users) | الاطلاع السريع على أخبار المدرسة وفعالياتها، معرفة أعضاء اللجنة، وإيصال أصواتهم ومقترحاتهم بسهولة عبر الهاتف. |
| **رئيس وأعضاء لجنة أولياء الأمور** | مالكو المشروع ومديرو المحتوى (Admins) | وجود قناة رسمية منظمة تمنع ضياع الرسائل في الدردشات، وتسهل جمع آراء الأهالي وتنظيم مشاركتهم في الفعاليات. |
| **إدارة مدرسة المحجر الابتدائية** | شريك استراتيجي ومستفيد غير مباشر | تعزيز الشراكة المجتمعية، ودعم الأنشطة المدرسية المشتركة عبر قنوات تواصل رسمية ومنضبطة. |
| **المطور / المهندس التقني** | المنفذ والمسؤول التقني | بناء نظام مستقر، سريع، وسهل الصيانة يعمل بكفاءة عالية ضمن قيود الاستضافة المجانية دون الحاجة لتدخل تقني يومي. |

---

## 7. الافتراضات والتبعيات (Assumptions and Dependencies)

### 7.1 الافتراضات (Assumptions)

* يمتلك غالبية أهالي الطلاب هواتف ذكية متصلة بالإنترنت وتطبيقات مراسلة (مثل WhatsApp) لاستقبال رابط المنصة.
* يتولى أحد أعضاء اللجنة المعيّنين مسؤولية إنشاء نماذج Google Forms عبر حساب Google الرسمي للجنة ونسخ روابط التضمين إلى لوحة تحكم المنصة.
* محتوى الإعلانات والفعاليات يركز على الشأن العام للمدرسة ولا يتضمن بيانات شخصية حساسة للطلاب القُصّر.

### 7.2 التبعيات الخارجية (Dependencies)

* **خدمات Google (Google Forms & Google Drive):** الاعتماد على استقرار وتوافر خوادم Google لاستقبال ردود الأهالي وتخزينها في جداول Google Sheets المرتبطة.
* **منصات استضافة الوسائط والتواصل الاجتماعي الخارجية:** الاعتماد على المنصات الخارجية المعتمدة لاستضافة وعرض الفيديو والريلز والمنشورات والصور والصوتيات (YouTube، Vimeo، Dailymotion، Instagram، Facebook، TikTok، X، Threads، LinkedIn، Telegram، SoundCloud، Spotify، Google Drive، Google Photos، Canva، وروابط الصور الخارجية الآمنة HTTPS).
* **منصة الاستضافة السحابية (PaaS Free Tier):** الاعتماد على مزود استضافة مجاني (مثل Vercel أو Netlify أو Render) لتشغيل التطبيق وتوفير شهادة SSL تلقائية.

---

## 8. القيود التقنية والتشغيلية (Constraints)

* **قيود الاستضافة المجانية (Free Hosting Tier):** محدودية سعة التخزين، عرض النطاق الترددي الشهري (Bandwidth)، وعدد ساعات تشغيل الخادم أو استدعاءات الدوال السحابية (Serverless Functions)؛ مما يفرض الاعتماد على التوليد الساكن (SSG/ISR) وتخزين الملفات الثقيلة خارجياً.
* **البنية التقنية المحددة:** الالتزام ببناء الواجهة الأمامية باستخدام **React / Next.js** والواجهة الخلفية باستخدام **Node.js** أو **Python (FastAPI/Flask)**.
* **عدم وجود ميزانية تشغيلية:** يجب أن تكون جميع الأدوات، قواعد البيانات (مثل Supabase أو MongoDB Atlas Free Tier أو ملفات JSON/Markdown عبر Git)، وخدمات النشر مجانية بالكامل.

---

## 9. معايير القبول (Acceptance Criteria)

يُعتبر المشروع مكتملاً ومقبولاً رسمياً عند تحقق جميع الشروط التالية:

1. **التجاوبية والعرض العربي:** فتح الرابط العام للمنصة على متصفحي Safari (iOS) وChrome (Android) بالإضافة إلى متصفح حاسوب مكتبي، والتأكد من سلامة التنسيق العربي (RTL) وعدم وجود أي تداخل بصري في النصوص أو الأزرار.
2. **عرض أعضاء اللجنة:** ظهور قائمة أعضاء لجنة أولياء أمور مدرسة المحجر الابتدائية بأسمائهم ووظائفهم بوضوح، وإمكانية تحديثها من لوحة الإدارة.
3. **نشر الفعاليات والوسائط:** نجاح نشر إعلان تجريبي يحتوي على نص، صورة، ورابط وسائط خارجية متنوعة (فيديو أو رييل من وسائل التواصل الاجتماعي أو منشور أو صورة خارجية)، وظهوره للزوار بشكل سليم.
4. **فعالية نماذج Google Forms:** القدرة على تعبئة وإرسال نموذج تجريبي (إبداء رأي / طلب مساعدة / تسجيل في فعالية) من داخل واجهة المنصة عبر الهاتف، ووصول البيانات بنجاح إلى جدول ردود اللجنة.
5. **أداء التحميل والتزامن:** اجتياز اختبار محاكاة الحمل (Load Testing) لـ 500 طلب متزامن بزمن استجابة متوسط أقل من 500ms دون أخطاء خادم (`5xx`).
6. **النشر الحي (Live Deployment):** استضافة التطبيق على نطاق عام مجاني مع تفعيل بروتوكول HTTPS، وتسليم بيانات الدخول للوحة الإدارة للجنة.
---
يمكنك استخدام الصيغة التالية مباشرة في موجه البرمجة لتطبيق **Mahjar Parents** (أو أي مهمة برمجية أخرى):

> Follow Test-Driven Development (TDD) strictly for all changes:
> 1. Write failing unit/integration tests first covering the requirements, edge cases, and failure modes before writing production code.
> 2. Implement the minimal code required to make the tests pass.
> 3. Refactor cleanly while keeping all tests green, without altering intended behavior or breaking existing tests.
> Do not skip writing tests first, and include the test suite and verification results in your response.
> 
> 


> Use strict TDD (Red-Green-Refactor): write the tests first and verify they fail, implement the code to pass them, then refactor while keeping all tests passing. Show the tests, implementation, and test output.

### Epic 1: Committee & Content Management

#### Story 1.1 – Committee Directory Display

* **Task 1.1.1 (React UI):** Build RTL-compliant, mobile-first committee member cards in React displaying full name, role/title, brief responsibility summary, and optional avatar image with accessible touch targets ($\ge 44 \times 44\text{px}$).
* **Task 1.1.2 (Flask API):** Implement `GET /api/committee` in Flask to return ordered committee member records and cache responses appropriately for fast reads.

#### Story 1.2 – Announcements & Events Feed

* **Task 1.2.1 (React UI):** Implement a reverse-chronological announcements and events feed in React with category filtering (`general`, `upcoming_event`, `student_activity`, `updates`) and responsive layout across mobile and desktop viewports.
* **Task 1.2.2 (Flask API):** Create `GET /api/posts` in Flask supporting category query parameters, pagination/ordering (newest first), and lightweight payloads to keep TTFB under `500ms`.

#### Story 1.3 – Embedded Multimedia & Image Optimization

* **Task 1.3.1 (Flask + OpenCV Pipeline):** Build an image-ingestion/optimization utility in Flask using **OpenCV** (`cv2`) to validate uploaded images, resize oversized dimensions, strip unnecessary metadata, and export compressed WebP/JPEG assets while validating and normalizing multi-type external media links (`video`, `reel`, `post`, `image`, `audio`) across trusted social/media platforms and safe public HTTPS external images without storing raw audio/video files on the server.
* **Task 1.3.2 (React UI):** Build media renderers in React that apply `loading="lazy"` to images and safely render allowlisted multi-type external media inside post detail views across three render modes (`iframe` for trusted embeddable players/reels/posts, `image` for safe external HTTPS images, and `card` for rich accessible preview cards) without bundling heavy media files into the hosting tier.

#### Story 1.4 – Protected Admin CMS

* **Task 1.4.1 (Flask Auth & CRUD):** Implement authenticated admin endpoints in Flask (`POST`/`PUT`/`DELETE` for committee members, posts, media links, and Google Forms embed URLs) protected via session/token authentication and strict URL/input sanitization against XSS and untrusted embed domains.
* **Task 1.4.2 (React Admin View):** Build a protected admin interface in React allowing committee editors to create, edit, and delete committee profiles, announcements, media links, and embedded form URLs without touching code.

---

### Epic 2: Community Engagement & Sharing

#### Story 2.1 – Embedded Google Forms Interaction

* **Task 2.1.1 (Flask Config API):** Expose active Google Forms configurations/URLs (feedback/suggestions, general issue/help requests, event registration) from Flask with domain validation restricted to trusted Google Forms URLs.
* **Task 2.1.2 (React Engagement View):** Create a zero-login engagement section in React rendering lazy-loaded Google Forms `<iframe>` embeds and direct fallback links on mobile and desktop.

#### Story 2.2 – WhatsApp Sharing

* **Task 2.2.1 (React Share Component):** Add a share action on each announcement and event card in React that constructs a URL-encoded WhatsApp share link (`[https://wa.me/?text=](https://wa.me/?text=)...` or Web Share API fallback) containing the post title and direct link.

---

### Epic 3: Platform Architecture, Performance & Security

#### Story 3.1 – Free-Tier Deployment & Security Hardening

* **Task 3.1.1 (Flask Security & CORS):** Configure Flask with HTTPS enforcement/headers, strict CORS rules, input sanitization, rate limiting on auth/write routes, and environment-based secrets for zero-budget/free-tier hosting.
* **Task 3.1.2 (React + Flask Free-Tier Packaging):** Configure build and deployment pipelines for React and Flask on free-tier hosting platforms, persisting lightweight structured data (e.g., JSON/SQLite/free-tier DB) and OpenCV-processed image assets while avoiding heavy server-side video/audio storage.

#### Story 3.2 – Responsiveness, RTL & Load Performance

* **Task 3.2.1 (React RTL & Mobile-First Styling):** Enforce `dir="rtl"`, Arabic typography, and mobile-first responsive breakpoints in React, verifying visual integrity across mobile (iOS/Android) and desktop browsers.
* **Task 3.2.2 (Performance & Concurrency Verification):** Run load and latency benchmarks simulating up to **500 concurrent users**, verifying average response times stay below **500ms** with zero `5xx` errors under free-tier resource limits.