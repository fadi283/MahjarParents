# تقرير التحقق من الأداء والتزامن – 500 مستخدم متزامن (Task 3.2.2)

يوثّق هذا التقرير منهجية ونتائج اختبارات التحمّل والتزامن لمنصة **لجنة أولياء أمور الطلاب – مدرسة المحجر الابتدائية** ضمن قيود الاستضافة المجانية (512 MB RAM، عملية Flask واحدة متعددة الخيوط، قاعدة بيانات SQLite بوضع WAL، وصور WebP المعالجة عبر OpenCV).

---

## 1. التحسينات الهندسية المطبقة للتزامن (Concurrency Hardening)

1. **حماية الذاكرة المؤقتة من التدافع (Cache Stampede & Race Protection):**
   - تأمين ذاكرات `/api/committee` و`/api/posts` و`/api/forms` في [`backend/app.py`](../backend/app.py) باستخدام أقفال `threading.Lock` مستقلة (`_committee_cache_lock`, `_posts_cache_lock`, `_forms_cache_lock`) وعدّاد أجيال (`generation`) يمنع كتابة استجابات قديمة بعد عمليات التعديل من لوحة الإدارة.
   - تحديد الحد الأقصى لعدد الاستجابات المخزنة في الذاكرة المؤقتة (`MAX_CACHE_RESPONSE_ENTRIES = 256`) لحماية استهلاك الذاكرة ضمن سقف `512 MB`.
2. **تحسين مسار الأمان الوسيط ([`backend/platform_security.py`](../backend/platform_security.py)):**
   - احتساب حدود الاستعلامات وJSON ورأس `Strict-Transport-Security` مرة واحدة عند تهيئة التطبيق بدلاً من إعادة تحليل الإعدادات في كل طلب HTTP.
3. **ضبط خادم Gunicorn للباقة المجانية ([`backend/gunicorn.conf.py`](../backend/gunicorn.conf.py)):**
   - تشغيل عامل واحد (`workers = 1`, `worker_class = "gthread"`) مع `threads = 8` و`backlog = 2048` لامتصاص ذروة الطلبات المتزامنة مع استهلاك ذاكرة منخفض.

---

## 2. بيئة القياس وسيناريو الاختبار (`backend/load_benchmark.py`)

- **نموذج الخادم:** خادم `BoundedThreadPoolWSGIServer` مقيّد بـ `server_threads = 8` و`request_queue_size = 512`، يشغّل التطبيق في وضع `MAHJAR_ENV=production` خلف `ProxyFix` (`X-Forwarded-Proto: https`) مع `SQLiteCMSStore` (WAL) وملف صورة WebP معالج بـ OpenCV و`SERVE_FRONTEND_DIST=True`.
- **نموذج الحمل:** `500` عميل HTTP متزامن يعملون في عملية معزولة (`asyncio` TCP sockets) لتجنب مشاركة GIL بين مولّد الحمل والخادم.
- **توزيعة الطلبات:**
  - `/api/posts` و`/api/posts?category=upcoming_event&limit=10`
  - `/api/committee`
  - `/api/forms`
  - `/api/media/images/<sha256>.webp`
  - `/` (واجهة React المبنية)
  - `/api/health`

---

## 3. النتائج المقاسة (500 مستخدم متزامن)

تم تشغيل الأمر:

```bash
/home/fadi/MahjarParents/venv/bin/python backend/load_benchmark.py --users 500 --requests-per-user 1 --storage sqlite
```

| المؤشر | القيمة المقاسة | معيار القبول (SRS / Task 3.2.2) | الحالة |
| --- | --- | --- | --- |
| إجمالي الطلبات المتزامنة | `500` طلب | `500` مستخدم متزامن | PASS |
| متوسط زمن الاستجابة (`avgMs`) | `269.84 ms` | `< 500 ms` | PASS |
| الوسيط (`p50Ms`) | `256.83 ms` | — | — |
| المئوي 95 (`p95Ms`) / 99 (`p99Ms`) | `500.96 ms` / `523.06 ms` | — | — |
| أقصى زمن استجابة (`maxMs`) | `526.51 ms` | — | — |
| معدل الإنتاجية (`Throughput`) | `905.54 req/s` (`0.552s`) | — | — |
| أخطاء الخادم (`5xx`) | `0` | `0` | PASS |
| أخطاء الاتصال (`conn`) | `0` | `0` | PASS |
| ذروة استهلاك الذاكرة (`peakRssMb`) | `101.83 MB` | `< 512 MB` | PASS |

### التحقق من القراءة والكتابة المتزامنة وموجات ETag 304
- تم التحقق ضمن [`backend/tests/test_performance_concurrency.py`](../backend/tests/test_performance_concurrency.py) من:
  - حماية البدء البارد (`50` خيطاً متزامناً على حاجز واحد = استدعاء واحد فقط للمصدر).
  - موجة `500` مستخدم بـ `1,000` طلب مع `ETag / 304 Not Modified` بمتوسط `< 500 ms` وصفر أخطاء `5xx`.
  - تزامن `100` قارئ عام مع `8` عمليات كتابة إدارية متزامنة على `SQLite WAL` دون أخطاء `5xx` أو قفل قاعدة البيانات.
