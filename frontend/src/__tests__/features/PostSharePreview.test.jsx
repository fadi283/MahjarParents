import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import path from 'node:path';
import { createRequire } from 'node:module';

import App, { resolvePageFromLocation } from '../../App.jsx';
import AnnouncementsFeed from '../../components/AnnouncementsFeed.jsx';
import {
  DEFAULT_SITE_META,
  applyDocumentMetaForPost,
  buildPostDocumentMeta,
} from '../../utils/documentMeta.js';

const require = createRequire(import.meta.url);
const postPreviewHandler = require(path.resolve(process.cwd(), '../api/post-preview.js'));

const samplePosts = [
  {
    id: 101,
    title: 'تعميم بخصوص مواعيد الدوام الشتوي',
    summary: 'نود إعلام الأهالي الكرام ببدء تطبيق التوقيت الشتوي.',
    category: 'general',
    publishedAt: '2026-11-10T08:00:00Z',
  },
  {
    id: 102,
    title: 'يوم التراث والهوية في مدرسة المحجر',
    summary: 'ملخص قصير ليوم التراث.',
    content: 'تفاصيل كاملة ليوم التراث السنوي في ساحة المدرسة بمشاركة جميع الطلاب والأهالي.',
    category: 'upcoming_event',
    publishedAt: '2026-11-24T10:30:00Z',
    eventDate: '2026-12-05',
    imageUrl: '/api/media/images/heritage123.webp',
  },
  {
    id: 103,
    title: 'مبادرة أصدقاء المكتبة',
    summary: 'انطلاق نشاط القراءة الأسبوعي.',
    category: 'student_activity',
    publishedAt: '2026-11-18T12:15:00Z',
  },
];

const SAMPLE_HTML_TEMPLATE = `<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="description"
    content="المنصة الرقمية للتواصل المجتمعي – لجنة أولياء أمور الطلاب في مدرسة المحجر الابتدائية: الإعلانات، الفعاليات، والنماذج التفاعلية للأهالي." />
  <meta property="og:type" content="website" />
  <meta property="og:locale" content="ar_AR" />
  <meta property="og:site_name" content="لجنة أولياء أمور الطلاب - مدرسة المحجر الابتدائية" />
  <meta property="og:title" content="لجنة أولياء أمور الطلاب - مدرسة المحجر الابتدائية" />
  <meta property="og:description"
    content="تابعوا أحدث إعلانات وفعاليات مدرسة المحجر الابتدائية، وشاركوا آراءكم وسجّلوا في الأنشطة المدرسية بسهولة." />
  <meta property="og:image" content="/logo.jpg" />
  <meta name="twitter:card" content="summary" />
  <meta name="twitter:title" content="لجنة أولياء أمور الطلاب - مدرسة المحجر الابتدائية" />
  <meta name="twitter:description"
    content="المنصة الرقمية للتواصل المجتمعي – لجنة أولياء أمور الطلاب في مدرسة المحجر الابتدائية." />
  <meta name="twitter:image" content="/logo.jpg" />
  <title>لجنة أولياء أمور الطلاب - مدرسة المحجر الابتدائية</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.jsx"></script>
</body>
</html>`;

test('App and AnnouncementsFeed render focused PostDetailView only when initialPostId / activePostId is provided', () => {
  const focusedAppHtml = renderToStaticMarkup(
    <App
      posts={samplePosts}
      initialPostId={102}
      shareBaseUrl="https://mahjar.example.org"
    />
  );

  assert.ok(focusedAppHtml.includes('يوم التراث والهوية في مدرسة المحجر'));
  assert.ok(
    focusedAppHtml.includes('تفاصيل كاملة ليوم التراث السنوي في ساحة المدرسة بمشاركة جميع الطلاب والأهالي.')
  );
  assert.ok(focusedAppHtml.includes('العودة إلى قائمة الإعلانات'));
  assert.match(
    focusedAppHtml,
    /data-share-url="https:\/\/mahjar\.example\.org\/posts\/102"/
  );
  assert.ok(
    !focusedAppHtml.includes('تعميم بخصوص مواعيد الدوام الشتوي'),
    'Focused post view must not render other unrelated posts from the feed'
  );
  assert.ok(
    !focusedAppHtml.includes('مبادرة أصدقاء المكتبة'),
    'Focused post view must not render other unrelated posts from the feed'
  );
});

test('AnnouncementsFeed renders accessible loading and not-found states for missing post IDs', () => {
  const loadingHtml = renderToStaticMarkup(
    <AnnouncementsFeed
      posts={samplePosts}
      activePostId="9999"
      isLoadingPost={true}
      onClosePost={() => {}}
    />
  );
  assert.match(loadingHtml, /role="status"/);
  assert.ok(loadingHtml.includes('جاري تحميل الإعلان'));

  const notFoundHtml = renderToStaticMarkup(
    <AnnouncementsFeed
      posts={samplePosts}
      activePostId="9999"
      isLoadingPost={false}
      onClosePost={() => {}}
    />
  );
  assert.match(notFoundHtml, /role="status"/);
  assert.ok(notFoundHtml.includes('الإعلان المطلوب غير موجود'));
  assert.ok(notFoundHtml.includes('العودة إلى قائمة الإعلانات'));
  assert.match(notFoundHtml, /min-height:\s*44px/);
  assert.match(notFoundHtml, /min-width:\s*44px/);
});

test('resolvePageFromLocation routes /posts/<id> to announcements and preserves hash navigation', () => {
  assert.equal(resolvePageFromLocation({ pathname: '/posts/102', hash: '', search: '' }), 'announcements');
  assert.equal(resolvePageFromLocation({ pathname: '/', hash: '#form-2', search: '' }), 'engagement');
  assert.equal(resolvePageFromLocation({ pathname: '/', hash: '#committee', search: '' }), 'committee');
  assert.equal(resolvePageFromLocation({ pathname: '/', hash: '', search: '?post=55' }), 'announcements');
});

test('applyDocumentMetaForPost updates document title and OG/Twitter tags for a post and restores site defaults when cleared', () => {
  const metaMap = new Map();
  const makeMeta = (attrName, attrValue, content = '') => ({
    attrs: { [attrName]: attrValue, content },
    setAttribute(k, v) {
      this.attrs[k] = v;
    },
    getAttribute(k) {
      return this.attrs[k] ?? null;
    },
  });

  for (const [attr, key, val] of [
    ['name', 'description', DEFAULT_SITE_META.description],
    ['property', 'og:type', 'website'],
    ['property', 'og:title', DEFAULT_SITE_META.title],
    ['property', 'og:description', DEFAULT_SITE_META.description],
    ['property', 'og:image', '/logo.jpg'],
    ['name', 'twitter:card', 'summary'],
    ['name', 'twitter:title', DEFAULT_SITE_META.title],
    ['name', 'twitter:description', DEFAULT_SITE_META.description],
    ['name', 'twitter:image', '/logo.jpg'],
  ]) {
    metaMap.set(`${attr}:${key}`, makeMeta(attr, key, val));
  }

  const fakeDoc = {
    title: DEFAULT_SITE_META.title,
    head: {
      appendChild(el) {
        const attr = el.getAttribute('property') ? 'property' : 'name';
        metaMap.set(`${attr}:${el.getAttribute(attr)}`, el);
      },
    },
    querySelector(selector) {
      const m = selector.match(/^meta\[(name|property)="([^"]+)"\]$/);
      if (!m) return null;
      return metaMap.get(`${m[1]}:${m[2]}`) ?? null;
    },
    createElement() {
      return makeMeta('name', '');
    },
  };

  const meta = buildPostDocumentMeta(samplePosts[1], {
    baseUrl: 'https://mahjar.example.org',
    apiBaseUrl: 'https://api.mahjar.example.org',
  });
  assert.ok(meta.title.includes('يوم التراث والهوية في مدرسة المحجر'));
  assert.equal(meta.url, 'https://mahjar.example.org/posts/102');
  assert.equal(meta.image, 'https://api.mahjar.example.org/api/media/images/heritage123.webp');

  const ytMeta = buildPostDocumentMeta(
    {
      id: 205,
      title: 'فيديو احتفالي',
      summary: 'ملخص.',
      mediaLinks: [{ mediaType: 'video', canonicalUrl: 'https://youtu.be/dQw4w9WgXcQ' }],
    },
    { baseUrl: 'https://mahjar.example.org' }
  );
  assert.equal(ytMeta.image, 'https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg');
  assert.equal(ytMeta.twitterCard, 'summary_large_image');

  applyDocumentMetaForPost(samplePosts[1], {
    doc: fakeDoc,
    baseUrl: 'https://mahjar.example.org',
    apiBaseUrl: 'https://api.mahjar.example.org',
  });
  assert.ok(fakeDoc.title.includes('يوم التراث والهوية في مدرسة المحجر'));
  assert.equal(metaMap.get('property:og:type').getAttribute('content'), 'article');
  assert.equal(metaMap.get('property:og:title').getAttribute('content'), 'يوم التراث والهوية في مدرسة المحجر');
  assert.equal(metaMap.get('property:og:url').getAttribute('content'), 'https://mahjar.example.org/posts/102');
  assert.equal(
    metaMap.get('property:og:image').getAttribute('content'),
    'https://api.mahjar.example.org/api/media/images/heritage123.webp'
  );
  assert.equal(metaMap.get('name:twitter:card').getAttribute('content'), 'summary_large_image');

  applyDocumentMetaForPost(null, {
    doc: fakeDoc,
    baseUrl: 'https://mahjar.example.org',
  });
  assert.equal(fakeDoc.title, DEFAULT_SITE_META.title);
  assert.equal(metaMap.get('property:og:type').getAttribute('content'), 'website');
  assert.equal(metaMap.get('property:og:title').getAttribute('content'), DEFAULT_SITE_META.title);
  assert.equal(metaMap.get('name:twitter:card').getAttribute('content'), 'summary');
});

test('Vercel post-preview function injects post OG/Twitter metadata, escapes XSS, resolves split-origin images, and falls back safely', async () => {
  const { buildPostPreviewHtml, createPostPreviewHandler } = postPreviewHandler;

  const built = buildPostPreviewHtml(
    SAMPLE_HTML_TEMPLATE,
    {
      id: 102,
      title: 'إعلان <script>alert(1)</script> "هام"',
      summary: 'ملخص الإعلان الجديد للأهالي.',
      publishedAt: '2026-11-24T10:30:00Z',
      imageUrl: '/api/media/images/photo99.webp',
    },
    {
      siteOrigin: 'https://mahjar.vercel.app',
      apiBaseUrl: 'https://mahjar-api.onrender.com',
    }
  );

  assert.ok(!built.includes('<script>alert(1)</script>'));
  assert.ok(built.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
  assert.ok(built.includes('property="og:type" content="article"'));
  assert.ok(built.includes('property="og:url" content="https://mahjar.vercel.app/posts/102"'));
  assert.ok(
    built.includes(
      'property="og:image" content="https://mahjar-api.onrender.com/api/media/images/photo99.webp?format=jpeg"'
    )
  );
  assert.ok(
    built.includes(
      'property="og:image:secure_url" content="https://mahjar-api.onrender.com/api/media/images/photo99.webp?format=jpeg"'
    )
  );
  assert.ok(built.includes('property="og:image:type" content="image/jpeg"'));
  assert.ok(built.includes('property="og:image:alt"'));
  assert.ok(built.includes('name="twitter:image:alt"'));
  assert.ok(built.includes('name="twitter:card" content="summary_large_image"'));
  assert.ok(built.includes('<div id="root"></div>'));
  assert.ok(!built.includes('تابعوا أحدث إعلانات وفعاليات'));

  const ytBuilt = buildPostPreviewHtml(
    SAMPLE_HTML_TEMPLATE,
    {
      id: 109,
      title: 'حفل المدرسة السنوي',
      summary: 'مقطع فيديو من الاحتفال.',
      mediaLinks: [{ mediaType: 'video', canonicalUrl: 'https://youtu.be/dQw4w9WgXcQ' }],
    },
    { siteOrigin: 'https://mahjar.vercel.app' }
  );
  assert.ok(
    ytBuilt.includes('property="og:image" content="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"')
  );
  assert.ok(ytBuilt.includes('property="og:image:width" content="480"'));
  assert.ok(ytBuilt.includes('property="og:image:height" content="360"'));
  assert.ok(ytBuilt.includes('name="twitter:card" content="summary_large_image"'));

  const makeRes = () => {
    const headers = {};
    let body = '';
    return {
      statusCode: 200,
      headers,
      get body() {
        return body;
      },
      setHeader(k, v) {
        headers[k.toLowerCase()] = v;
      },
      status(code) {
        this.statusCode = code;
        return this;
      },
      send(text) {
        body = text;
        return this;
      },
    };
  };

  // Valid backend response
  const okHandler = createPostPreviewHandler({
    apiBaseUrlOverride: 'https://mahjar-api.onrender.com',
    loadTemplateHtml: async () => SAMPLE_HTML_TEMPLATE,
    fetchImpl: async (url) => {
      assert.equal(url, 'https://mahjar-api.onrender.com/api/posts/102');
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: 102,
          title: 'فعالية يوم التراث',
          summary: 'برنامج اليوم التراثي الكامل.',
          imageUrl: '',
        }),
      };
    },
  });

  const okRes = makeRes();
  await okHandler(
    {
      query: { id: '102' },
      headers: { host: 'mahjar.vercel.app', 'x-forwarded-proto': 'https' },
    },
    okRes
  );
  assert.equal(okRes.statusCode, 200);
  assert.equal(okRes.headers['content-type'], 'text/html; charset=utf-8');
  assert.equal(okRes.headers['x-content-type-options'], 'nosniff');
  assert.equal(okRes.headers['x-frame-options'], 'DENY');
  assert.ok(okRes.body.includes('property="og:title" content="فعالية يوم التراث"'));
  assert.ok(okRes.body.includes('property="og:image" content="https://mahjar.vercel.app/logo.jpg"'));
  assert.ok(okRes.body.includes('name="twitter:card" content="summary"'));

  // 404 or network error or invalid ID -> falls back cleanly to base index.html with 200
  const fallbackHandler = createPostPreviewHandler({
    apiBaseUrlOverride: 'https://mahjar-api.onrender.com',
    loadTemplateHtml: async () => SAMPLE_HTML_TEMPLATE,
    fetchImpl: async () => {
      throw new Error('Upstream timeout');
    },
  });

  const errRes = makeRes();
  await fallbackHandler(
    {
      query: { id: '102' },
      headers: { host: 'mahjar.vercel.app', 'x-forwarded-proto': 'https' },
    },
    errRes
  );
  assert.equal(errRes.statusCode, 200);
  assert.equal(errRes.body, SAMPLE_HTML_TEMPLATE);

  const badIdRes = makeRes();
  await okHandler(
    {
      query: { id: '../etc/passwd' },
      headers: { host: 'mahjar.vercel.app', 'x-forwarded-proto': 'https' },
    },
    badIdRes
  );
  assert.equal(badIdRes.statusCode, 200);
  assert.equal(badIdRes.body, SAMPLE_HTML_TEMPLATE);
});
