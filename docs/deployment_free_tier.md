# دليل التغليف والنشر المجاني (Free-Tier Deployment Guide)

يوثّق هذا الدليل إعدادات البناء والنشر لمنصة **لجنة أولياء أمور الطلاب – مدرسة المحجر الابتدائية** على منصات الاستضافة السحابية المجانية، مع حفظ البيانات المهيكلة الخفيفة (JSON / SQLite) والصور المعالجة عبر OpenCV فقط دون تخزين ملفات فيديو أو صوت خام على الخادم.

---

## 1. خيارات النشر المجاني (Deployment Topologies)

### الخيار أ: النشر المنفصل (Split PaaS — موصى به للأداء المجاني)
- **الواجهة الأمامية (React + Vite):** تُنشر كملفات ساكنة على **Vercel** (`vercel.json`) أو **Netlify** (`netlify.toml`) أو **Render Static Site** (`render.yaml`).
  - أمر البناء: `cd frontend && npm ci && npm run build && npm run build:verify`
  - متغير البيئة المطلوب: `VITE_API_BASE_URL=https://<your-flask-service>.onrender.com`
- **الواجهة الخلفية (Flask + OpenCV-headless + Gunicorn):** تُنشر على **Render Free Web Service** (`render.yaml`) أو Railway / Fly.io عبر `Procfile` و `backend/gunicorn.conf.py`.

### الخيار ب: حاوية واحدة موحدة (Single-Service Docker)
- يبني `Dockerfile` واجهة React أولاً داخل `node:22-alpine` ثم يدمج `frontend/dist` مع خادم Flask/Gunicorn داخل `python:3.12-slim` مع تفعيل:
  - `MAHJAR_SERVE_FRONTEND=true`
  - `MAHJAR_STORAGE_BACKEND=sqlite`
  - `MAHJAR_DATA_DIR=/var/data`

---

## 2. حفظ البيانات والوسائط ضمن قيود الباقة المجانية

1. **البيانات المهيكلة (SQLite WAL / JSON):**
   - يدعم النظام كلاً من `CMSStore` (ملف JSON ذري) و `SQLiteCMSStore` (SQLite بوضع `WAL` لضمان عدم تعارض الكتابة المتزامنة).
   - للترحيل من JSON إلى SQLite، تتوفر الدالة `cms_store.migrate_json_to_sqlite(json_path, sqlite_path)`.
2. **الصور المحسّنة عبر OpenCV (`opencv-python-headless`):**
   - تُعاد ترميز الصور المرفوعة إلى WebP/JPEG مع إزالة البيانات الوصفية (EXIF) وتصغير الأبعاد (`<= 1280px`) وتخزينها بأسماء محتوى SHA-256 داخل `MAHJAR_MEDIA_UPLOAD_DIR` (أو `<MAHJAR_DATA_DIR>/uploads/images`).
   - تُفرض حصة تخزين مجانية عبر `MAHJAR_MAX_MEDIA_STORAGE_BYTES` (الافتراضي `52428800` بايت = 50 MiB)، ويُرفض أي رفع يتجاوزها برمز `507 STORAGE_QUOTA_EXCEEDED`.
3. **منع تخزين الفيديو والصوت الخام:**
   - يرفض الخادم وبرامج التحقق (`verify-dist.js` و `media_pipeline.py`) أي ملفات `.mp4`/`.mp3`/`.wav`/إلخ (`415 RAW_AV_NOT_ALLOWED`)، ويُكتفى بروابط التضمين الخارجية الموثوقة (YouTube، Vimeo، SoundCloud، Google Drive).

---

## 3. نقاط الفحص والتشغيل (Health & Readiness)

- `GET /api/health` → فحص حيوية سريع (`200 OK`) لـ Render / Docker Healthcheck.
- `GET /api/ready` → يعرض حالة مخزن البيانات (`json`/`sqlite`)، استخدام حصة الصور، وتأكيد `rawAvStorageAllowed: false` دون كشف أي أسرار أو مسارات داخلية.

---

## 4. التحقق من الأداء والتزامن (500 مستخدم)

- لمتابعة تفاصيل اختبار التحمّل وتشغيله محلياً أو ضمن CI، راجع [تقرير الأداء والتزامن (Task 3.2.2)](./performance_benchmark_report.md) وأداة القياس [`backend/load_benchmark.py`](../backend/load_benchmark.py).
