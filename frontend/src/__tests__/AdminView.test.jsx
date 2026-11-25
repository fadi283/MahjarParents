import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import {
  ADMIN_POST_CATEGORY_OPTIONS,
  FORM_TYPE_LABELS,
  FORM_TYPE_OPTIONS,
  sanitizeAdminText,
  validateCommitteeInput,
  validateGoogleFormInput,
  validateGoogleFormUrl,
  validateMediaLinkInput,
  validatePostInput,
} from '../utils/adminValidation.js';
import {
  ADMIN_TOKEN_STORAGE_KEY,
  AdminApiError,
  createAdminApiClient,
  translateAdminError,
} from '../utils/adminApi.js';
import {
  removeById,
  syncMediaLinksIntoPosts,
  upsertCommitteeList,
  upsertFormList,
  upsertMediaLinkList,
  upsertPostList,
} from '../utils/adminState.js';
import AdminLoginForm from '../components/admin/AdminLoginForm.jsx';
import CommitteeAdminPanel from '../components/admin/CommitteeAdminPanel.jsx';
import PostsAdminPanel from '../components/admin/PostsAdminPanel.jsx';
import MediaLinksAdminPanel from '../components/admin/MediaLinksAdminPanel.jsx';
import FormsAdminPanel from '../components/admin/FormsAdminPanel.jsx';
import AdminDashboard, { ADMIN_SECTIONS } from '../components/admin/AdminDashboard.jsx';
import App from '../App.jsx';

function createMemoryStorage(initialEntries = {}) {
  const store = new Map(Object.entries(initialEntries));
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
    removeItem(key) {
      store.delete(key);
    },
  };
}

function makeMockResponse(status, data) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get(name) {
        return name.toLowerCase() === 'content-type' ? 'application/json' : null;
      },
    },
    async json() {
      return data;
    },
    async text() {
      return JSON.stringify(data);
    },
  };
}

// --- 1. Client-side Validation & XSS/URL Allowlist Tests ---

test('sanitizeAdminText strips dangerous HTML blocks, tags, script URIs, and angle brackets', () => {
  assert.equal(
    sanitizeAdminText('أحمد <script>alert(1)</script> <b>محمود</b>'),
    'أحمد محمود'
  );
  assert.equal(
    sanitizeAdminText('نص <img src=x onerror=alert(1)> آمن <svg onload=alert(1)></svg>'),
    'نص آمن'
  );
  assert.equal(
    sanitizeAdminText('javascript:alert(1) مرحبا'),
    'alert(1) مرحبا'
  );
  assert.equal(
    sanitizeAdminText('السطر الأول\r\n<script>x</script>\nالسطر الثاني', { allowNewlines: true }),
    'السطر الأول\nالسطر الثاني'
  );
});

test('validateGoogleFormUrl accepts trusted docs.google.com/forms HTTPS URLs, preserves entry params, and rejects untrusted/unsafe URLs', () => {
  const published = validateGoogleFormUrl(
    'https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform?usp=sf_link&entry.1001=التراث'
  );
  assert.equal(published.valid, true);
  assert.equal(published.provider, 'google_forms');
  assert.equal(published.formId, '1FAIpQLScAbCdEfGhIjKlMnOpQr');
  assert.ok(published.embedUrl.includes('embedded=true'));
  assert.ok(published.embedUrl.includes('entry.1001='));
  assert.ok(!published.embedUrl.includes('usp='));
  assert.equal(
    published.canonicalUrl,
    'https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform?entry.1001=%D8%A7%D9%84%D8%AA%D8%B1%D8%A7%D8%AB'
  );

  const shortForm = validateGoogleFormUrl(
    'https://docs.google.com/forms/u/0/d/1FAIpQLScAbCdEfGhIjKlMnOpQr'
  );
  assert.equal(shortForm.valid, true);
  assert.equal(
    shortForm.embedUrl,
    'https://docs.google.com/forms/d/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform?embedded=true'
  );

  const shortGle = validateGoogleFormUrl('https://forms.gle/fajYrbhcTA3xZa8d9');
  assert.equal(shortGle.valid, true);
  assert.equal(shortGle.provider, 'google_forms');
  assert.equal(shortGle.formId, 'fajYrbhcTA3xZa8d9');
  assert.equal(shortGle.canonicalUrl, 'https://forms.gle/fajYrbhcTA3xZa8d9');
  assert.equal(shortGle.embedUrl, 'https://forms.gle/fajYrbhcTA3xZa8d9');

  const shortGleWithQuery = validateGoogleFormUrl(
    'https://forms.gle/fajYrbhcTA3xZa8d9/?usp=sf_link'
  );
  assert.equal(shortGleWithQuery.valid, true);
  assert.equal(shortGleWithQuery.canonicalUrl, 'https://forms.gle/fajYrbhcTA3xZa8d9');
  assert.equal(shortGleWithQuery.embedUrl, 'https://forms.gle/fajYrbhcTA3xZa8d9');

  const rejected = [
    '',
    'http://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform',
    'https://forms.gle.evil.com/fajYrbhcTA3xZa8d9',
    'http://forms.gle/fajYrbhcTA3xZa8d9',
    'https://forms.gle/short',
    'https://forms.gle/fajYrbhcTA3xZa8d9/extra',
    'https://docs.google.com.evil.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform',
    'https://docs.google.com/document/d/1FAIpQLScAbCdEfGhIjKlMnOpQr/edit',
    'javascript:alert(1)',
    'https://user:pass@docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform',
    'https://docs.google.com:8443/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform',
    'https://docs.google.com/forms/d/e/../1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform',
  ];

  for (const badUrl of rejected) {
    const res = validateGoogleFormUrl(badUrl);
    assert.equal(res.valid, false, `Expected Google Form URL to be rejected: ${badUrl}`);
    assert.ok(res.error, 'Rejected Google Form URL must provide an Arabic error message');
  }
});

test('validateCommitteeInput sanitizes XSS, validates required/optional fields, and converts displayOrder cleanly', () => {
  const validResult = validateCommitteeInput({
    fullName: 'سمير <b>محمود</b> <script>alert(1)</script> عودة',
    role: 'عضو <img src=x onerror=alert(1)> لجنة',
    responsibilitySummary: 'متابعة <svg onload=alert(1)></svg> الأنشطة الطلابية.',
    email: 'samir@mahjar.org',
    phone: '052-1112233',
    avatarUrl: '/api/media/images/0123456789abcdef.webp',
    displayOrder: '3',
  });

  assert.equal(validResult.valid, true);
  assert.deepEqual(validResult.payload, {
    fullName: 'سمير محمود عودة',
    role: 'عضو لجنة',
    responsibilitySummary: 'متابعة الأنشطة الطلابية.',
    email: 'samir@mahjar.org',
    phone: '052-1112233',
    avatarUrl: '/api/media/images/0123456789abcdef.webp',
    displayOrder: 3,
  });

  const emptyOrderResult = validateCommitteeInput({
    fullName: 'نورا خالد',
    role: 'عضو لجنة',
    displayOrder: '   ',
  });
  assert.equal(emptyOrderResult.valid, true);
  assert.equal(emptyOrderResult.payload.displayOrder, null);

  const badCases = [
    { fullName: '<script>alert(1)</script>', role: 'عضو' },
    { fullName: 'س', role: 'عضو لجنة' },
    { fullName: 'عضو صالح', role: 'ع' },
    { fullName: 'عضو صالح', role: 'عضو', email: 'invalid-email' },
    { fullName: 'عضو صالح', role: 'عضو', phone: 'abc' },
    { fullName: 'عضو صالح', role: 'عضو', avatarUrl: 'javascript:alert(1)' },
    { fullName: 'عضو صالح', role: 'عضو', avatarUrl: 'https://example.com/avatar.svg' },
    { fullName: 'عضو صالح', role: 'عضو', avatarUrl: 'https://example.com/clip.mp4' },
    { fullName: 'عضو صالح', role: 'عضو', displayOrder: '0' },
    { fullName: 'عضو صالح', role: 'عضو', displayOrder: '-2' },
    { fullName: 'عضو صالح', role: 'عضو', displayOrder: 'abc' },
  ];

  for (const input of badCases) {
    const res = validateCommitteeInput(input);
    assert.equal(res.valid, false, `Expected invalid committee input: ${JSON.stringify(input)}`);
    assert.ok(Object.keys(res.errors).length > 0);
  }
});

test('validatePostInput validates categories, calendar event dates, safe image URLs, and XSS stripping', () => {
  assert.equal(ADMIN_POST_CATEGORY_OPTIONS.length, 4);

  const valid = validatePostInput({
    title: 'اجتماع <script>alert(1)</script> أولياء الأمور',
    summary: 'دعوة عامة\n<b>لجميع الأهالي</b> للحضور.',
    category: 'upcoming_event',
    eventDate: '2026-12-10',
    imageUrl: 'https://cdn.example.com/flyer.webp',
  });
  assert.equal(valid.valid, true);
  assert.equal(valid.payload.title, 'اجتماع أولياء الأمور');
  assert.equal(valid.payload.summary, 'دعوة عامة\nلجميع الأهالي للحضور.');
  assert.equal(valid.payload.category, 'upcoming_event');
  assert.equal(valid.payload.eventDate, '2026-12-10');
  assert.equal(valid.payload.imageUrl, 'https://cdn.example.com/flyer.webp');

  const invalidCases = [
    { title: '', summary: 'ملخص', category: 'general' },
    { title: 'عنوان', summary: '', category: 'general' },
    { title: 'عنوان', summary: 'ملخص', category: 'unknown_category' },
    { title: 'عنوان', summary: 'ملخص', category: 'general', eventDate: '10-12-2026' },
    { title: 'عنوان', summary: 'ملخص', category: 'general', eventDate: '2026-02-30' },
    { title: 'عنوان', summary: 'ملخص', category: 'general', imageUrl: 'http://insecure.com/a.webp' },
    { title: 'عنوان', summary: 'ملخص', category: 'general', imageUrl: 'javascript:alert(1)' },
    { title: 'عنوان', summary: 'ملخص', category: 'general', imageUrl: 'https://example.com/a.svg' },
  ];

  for (const input of invalidCases) {
    const res = validatePostInput(input);
    assert.equal(res.valid, false, `Expected invalid post input: ${JSON.stringify(input)}`);
  }
});

test('validateMediaLinkInput accepts allowlisted media URLs, handles optional mediaType/postId, and rejects untrusted/mismatched inputs', () => {
  const autoYouTube = validateMediaLinkInput({
    url: 'https://youtu.be/dQw4w9WgXcQ',
    title: 'كلمة <b>ترحيبية</b>',
    mediaType: '',
    postId: '2',
  });
  assert.equal(autoYouTube.valid, true);
  assert.equal('mediaType' in autoYouTube.payload, false, 'Empty mediaType should be omitted');
  assert.equal(autoYouTube.payload.postId, 2);
  assert.equal(autoYouTube.payload.title, 'كلمة ترحيبية');
  assert.equal(autoYouTube.resolved.provider, 'youtube');

  const standaloneDrive = validateMediaLinkInput({
    url: 'https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/view',
    mediaType: 'audio',
    postId: '',
  });
  assert.equal(standaloneDrive.valid, true);
  assert.equal(standaloneDrive.payload.mediaType, 'audio');
  assert.equal(standaloneDrive.payload.postId, null);

  const rejected = [
    { url: 'https://evil.example.com/video.mp4' },
    { url: 'http://www.youtube.com/watch?v=dQw4w9WgXcQ' },
    { url: 'javascript:alert(1)' },
    { url: 'https://soundcloud.com/school/anthem', mediaType: 'video' },
    { url: 'https://youtu.be/dQw4w9WgXcQ', postId: '0' },
    { url: 'https://youtu.be/dQw4w9WgXcQ', postId: 'abc' },
  ];

  for (const input of rejected) {
    const res = validateMediaLinkInput(input);
    assert.equal(res.valid, false, `Expected invalid media link: ${JSON.stringify(input)}`);
  }
});

test('validateGoogleFormInput validates formType, title, description, embedUrl, strict boolean active, and displayOrder', () => {
  assert.deepEqual(FORM_TYPE_OPTIONS.map((item) => item.id), [
    'feedback',
    'help_request',
    'event_registration',
  ]);
  assert.ok(FORM_TYPE_LABELS.feedback);

  const valid = validateGoogleFormInput({
    formType: 'event_registration',
    title: 'التسجيل <script>x</script> في الفعالية',
    description: 'يرجى <b>التسجيل</b> قبل الخميس.',
    embedUrl: 'https://docs.google.com/forms/d/e/1FAIpQLSeValidForm123456/viewform',
    active: false,
    displayOrder: '4',
  });
  assert.equal(valid.valid, true);
  assert.deepEqual(valid.payload, {
    formType: 'event_registration',
    title: 'التسجيل في الفعالية',
    description: 'يرجى التسجيل قبل الخميس.',
    embedUrl: 'https://docs.google.com/forms/d/e/1FAIpQLSeValidForm123456/viewform?embedded=true',
    active: false,
    displayOrder: 4,
  });

  const invalid = validateGoogleFormInput({
    formType: 'invalid_type',
    title: 'س',
    embedUrl: 'https://evil.com/form',
    active: 'yes',
    displayOrder: '-1',
  });
  assert.equal(invalid.valid, false);
  assert.ok(invalid.errors.formType);
  assert.ok(invalid.errors.title);
  assert.ok(invalid.errors.embedUrl);
  assert.ok(invalid.errors.active);
  assert.ok(invalid.errors.displayOrder);
});

// --- 2. Authenticated Admin API Client Tests ---

test('createAdminApiClient manages login, Bearer token storage, session checks, logout, and 401 token eviction', async () => {
  const calls = [];
  const storage = createMemoryStorage();
  let mode = 'ok';

  const mockFetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url === '/api/admin/auth/login') {
      return makeMockResponse(200, {
        authenticated: true,
        username: 'admin',
        token: 'signed-bearer-token-123',
        tokenType: 'Bearer',
        expiresIn: 3600,
      });
    }
    if (url === '/api/admin/auth/me' && mode === 'expired') {
      return makeMockResponse(401, {
        error: 'Admin authentication token has expired.',
        code: 'TOKEN_EXPIRED',
      });
    }
    if (url === '/api/admin/auth/me') {
      return makeMockResponse(200, {
        authenticated: true,
        username: 'admin',
        authMethod: 'bearer',
      });
    }
    if (url === '/api/admin/auth/logout') {
      return makeMockResponse(200, { authenticated: false, loggedOut: true });
    }
    return makeMockResponse(200, []);
  };

  const api = createAdminApiClient({ fetchImpl: mockFetch, storage });

  const loginRes = await api.login('admin', 'secret');
  assert.equal(loginRes.authenticated, true);
  assert.equal(storage.getItem(ADMIN_TOKEN_STORAGE_KEY), 'signed-bearer-token-123');
  assert.equal(calls[0].options.credentials, 'include');

  const meRes = await api.getSession();
  assert.equal(meRes.username, 'admin');
  assert.equal(calls[1].options.headers.Authorization, 'Bearer signed-bearer-token-123');
  assert.equal(calls[1].options.credentials, 'include');

  mode = 'expired';
  await assert.rejects(
    () => api.getSession(),
    (err) => err instanceof AdminApiError && err.status === 401 && err.isAuthError === true
  );
  assert.equal(storage.getItem(ADMIN_TOKEN_STORAGE_KEY), null, '401 must clear stored token');

  await api.login('admin', 'secret');
  assert.equal(storage.getItem(ADMIN_TOKEN_STORAGE_KEY), 'signed-bearer-token-123');
  await api.logout();
  assert.equal(storage.getItem(ADMIN_TOKEN_STORAGE_KEY), null, 'logout must clear stored token');
});

test('createAdminApiClient calls exact Flask CRUD and image upload endpoints', async () => {
  const calls = [];
  const storage = createMemoryStorage({ [ADMIN_TOKEN_STORAGE_KEY]: 'tok-abc' });

  const mockFetch = async (url, options = {}) => {
    calls.push({ url, options });
    return makeMockResponse(200, { ok: true });
  };

  const api = createAdminApiClient({ fetchImpl: mockFetch, storage });

  await api.listCommittee();
  await api.createCommitteeMember({ fullName: 'أحمد', role: 'عضو' });
  await api.updateCommitteeMember(5, { role: 'نائب' });
  await api.deleteCommitteeMember(5);

  await api.listPosts();
  await api.createPost({ title: 'إعلان', summary: 'ملخص', category: 'general' });
  await api.updatePost(9, { title: 'معدل' });
  await api.deletePost(9);

  await api.listMediaLinks();
  await api.listMediaLinks(9);
  await api.createMediaLink({ url: 'https://youtu.be/dQw4w9WgXcQ' });
  await api.updateMediaLink(3, { title: 'فيديو' });
  await api.deleteMediaLink(3);

  await api.listForms();
  await api.createForm({ formType: 'feedback', title: 'رأي', embedUrl: 'https://docs.google.com/forms/d/e/1234567890ab/viewform' });
  await api.updateForm(2, { active: false });
  await api.deleteForm(2);

  await api.uploadImage({ name: 'photo.png' });

  const expected = [
    ['GET', '/api/admin/committee'],
    ['POST', '/api/admin/committee'],
    ['PUT', '/api/admin/committee/5'],
    ['DELETE', '/api/admin/committee/5'],
    ['GET', '/api/admin/posts'],
    ['POST', '/api/admin/posts'],
    ['PUT', '/api/admin/posts/9'],
    ['DELETE', '/api/admin/posts/9'],
    ['GET', '/api/admin/media-links'],
    ['GET', '/api/admin/media-links?post_id=9'],
    ['POST', '/api/admin/media-links'],
    ['PUT', '/api/admin/media-links/3'],
    ['DELETE', '/api/admin/media-links/3'],
    ['GET', '/api/admin/forms'],
    ['POST', '/api/admin/forms'],
    ['PUT', '/api/admin/forms/2'],
    ['DELETE', '/api/admin/forms/2'],
    ['POST', '/api/media/images'],
  ];

  assert.equal(calls.length, expected.length);
  expected.forEach(([method, url], index) => {
    assert.equal(calls[index].options.method, method);
    assert.equal(calls[index].url, url);
    assert.equal(calls[index].options.headers.Authorization, 'Bearer tok-abc');
  });
  assert.ok(calls[calls.length - 1].options.body instanceof FormData);
});

test('translateAdminError maps backend error codes to Arabic messages', () => {
  assert.ok(translateAdminError({ code: 'INVALID_CREDENTIALS' }).includes('اسم المستخدم'));
  assert.ok(translateAdminError({ code: 'TOKEN_EXPIRED' }).includes('انتهت'));
  assert.ok(translateAdminError({ code: 'UNTRUSTED_FORM_DOMAIN' }).includes('Google Forms'));
  assert.ok(translateAdminError({ code: 'UNTRUSTED_MEDIA_DOMAIN' }).includes('المعتمدة'));
  assert.ok(translateAdminError({ code: 'RAW_AV_NOT_ALLOWED' }).includes('خارجياً'));
  assert.ok(translateAdminError({ code: 'FILE_TOO_LARGE' }).includes('حجم'));
});

// --- 3. Pure Admin State Helpers Tests ---

test('adminState helpers upsert, remove, order, and sync media links into posts', () => {
  const committee = upsertCommitteeList(
    [{ id: 1, fullName: 'ب', role: 'عضو', displayOrder: 2 }],
    { id: 2, fullName: 'أ', role: 'رئيس', displayOrder: 1 }
  );
  assert.deepEqual(committee.map((m) => m.id), [2, 1]);

  const posts = upsertPostList(
    [{ id: 1, title: 'قديم', publishedAt: '2026-11-01T08:00:00Z' }],
    { id: 2, title: 'جديد', publishedAt: '2026-11-24T08:00:00Z' }
  );
  assert.deepEqual(posts.map((p) => p.id), [2, 1]);

  const media = upsertMediaLinkList(
    [{ id: 10, postId: 1, title: 'أول' }],
    { id: 10, postId: 2, title: 'محدّث' }
  );
  assert.equal(media.length, 1);
  assert.equal(media[0].postId, 2);

  const syncedPosts = syncMediaLinksIntoPosts(posts, media);
  assert.equal(syncedPosts[0].mediaLinks.length, 1);
  assert.equal(syncedPosts[0].mediaLinks[0].title, 'محدّث');
  assert.equal(syncedPosts[1].mediaLinks.length, 0);

  const forms = upsertFormList(
    [{ id: 1, title: 'ثاني', displayOrder: 2 }],
    { id: 2, title: 'أول', displayOrder: 1 }
  );
  assert.deepEqual(forms.map((f) => f.id), [2, 1]);

  assert.deepEqual(removeById(forms, 2).map((f) => f.id), [1]);
});

// --- 4. React SSR & Protected Admin UI Tests ---

test('AdminLoginForm renders accessible RTL login form with >= 44x44px submit button', () => {
  const html = renderToStaticMarkup(
    <AdminLoginForm onLogin={() => {}} onCancel={() => {}} error="بيانات الدخول غير صحيحة." />
  );

  assert.match(html, /dir="rtl"/);
  assert.ok(html.includes('تسجيل الدخول إلى لوحة الإدارة'));
  assert.match(html, /<label[^>]*for="admin-username"/);
  assert.match(html, /<input[^>]*id="admin-username"/);
  assert.match(html, /<label[^>]*for="admin-password"/);
  assert.match(html, /<input[^>]*id="admin-password"[^>]*type="password"/);
  assert.ok(html.includes('بيانات الدخول غير صحيحة.'));
  assert.match(html, /role="alert"/);
  assert.match(html, /min-height:\s*44px/);
  assert.match(html, /min-width:\s*44px/);
});

test('Unauthenticated AdminDashboard strictly hides all CRUD tabs, forms, and management panels', () => {
  const html = renderToStaticMarkup(<AdminDashboard />);

  assert.match(html, /dir="rtl"/);
  assert.ok(html.includes('تسجيل الدخول إلى لوحة الإدارة'));
  assert.doesNotMatch(html, /role="tablist"/);
  assert.doesNotMatch(html, /class="admin-panel"/);
  assert.ok(!html.includes('إضافة عضو لجنة جديد'));
  assert.ok(!html.includes('إضافة إعلان أو فعالية جديدة'));
  assert.ok(!html.includes('إضافة رابط وسائط خارجي'));
  assert.ok(!html.includes('إضافة رابط Google Form جديد'));
  assert.ok(!html.includes('حفظ التعديلات'));
  assert.ok(!html.includes('تأكيد الحذف'));
});

test('Authenticated AdminDashboard renders header, logout, 4 accessible tabs, and active section content', () => {
  assert.equal(ADMIN_SECTIONS.length, 4);

  const initialData = {
    committee: [
      { id: 1, fullName: 'فادي وليد اغبارية', role: 'رئيس لجنة أولياء أمور الطلاب', email: 'Egb.fadi@gmail.com' },
    ],
    posts: [
      { id: 1, title: 'يوم التراث والهوية', summary: 'ملخص', category: 'upcoming_event', mediaLinks: [] },
    ],
    mediaLinks: [
      { id: 1, postId: 1, title: 'فيديو اليوم', mediaType: 'video', provider: 'youtube', canonicalUrl: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' },
    ],
    forms: [
      {
        id: 1,
        formType: 'feedback',
        title: 'نموذج إبداء الرأي',
        description: 'وصف النموذج',
        embedUrl: 'https://docs.google.com/forms/d/e/1FAIpQLScMahjarFeedbackDefault01/viewform?embedded=true',
        active: true,
        displayOrder: 1,
      },
    ],
  };

  const baseHtml = renderToStaticMarkup(
    <AdminDashboard
      initialAuth={{ authenticated: true, username: 'admin' }}
      initialData={initialData}
      initialSection="committee"
      onExitAdmin={() => {}}
    />
  );

  assert.match(baseHtml, /dir="rtl"/);
  assert.ok(baseHtml.includes('لوحة إدارة محتوى اللجنة'));
  assert.ok(baseHtml.includes('admin'));
  assert.ok(baseHtml.includes('تسجيل الخروج'));
  assert.ok(baseHtml.includes('العودة للمنصة'));
  assert.match(baseHtml, /role="tablist"/);
  assert.ok(baseHtml.includes('أعضاء اللجنة'));
  assert.ok(baseHtml.includes('الإعلانات والفعاليات'));
  assert.ok(baseHtml.includes('روابط الوسائط'));
  assert.ok(baseHtml.includes('نماذج Google Forms'));
  assert.ok(baseHtml.includes('فادي وليد اغبارية'));
  assert.match(baseHtml, /min-height:\s*44px/);
  assert.match(baseHtml, /min-width:\s*44px/);

  const postsHtml = renderToStaticMarkup(
    <AdminDashboard
      initialAuth={{ authenticated: true, username: 'admin' }}
      initialData={initialData}
      initialSection="posts"
    />
  );
  assert.ok(postsHtml.includes('يوم التراث والهوية'));
  assert.ok(postsHtml.includes('إضافة إعلان أو فعالية جديدة'));

  const mediaHtml = renderToStaticMarkup(
    <AdminDashboard
      initialAuth={{ authenticated: true, username: 'admin' }}
      initialData={initialData}
      initialSection="media"
    />
  );
  assert.ok(mediaHtml.includes('فيديو اليوم'));
  assert.ok(mediaHtml.includes('إضافة رابط وسائط خارجي'));

  const formsHtml = renderToStaticMarkup(
    <AdminDashboard
      initialAuth={{ authenticated: true, username: 'admin' }}
      initialData={initialData}
      initialSection="forms"
    />
  );
  assert.ok(formsHtml.includes('نموذج إبداء الرأي'));
  assert.ok(formsHtml.includes('إضافة رابط Google Form جديد'));
});

test('Admin CRUD panels support edit mode with save/cancel actions and accessible buttons', () => {
  const committeeEditHtml = renderToStaticMarkup(
    <CommitteeAdminPanel
      members={[{ id: 1, fullName: 'عضو أول', role: 'عضو لجنة' }]}
      initialEditingItem={{ id: 1, fullName: 'عضو أول', role: 'عضو لجنة', email: 'a@b.com' }}
    />
  );
  assert.ok(committeeEditHtml.includes('حفظ التعديلات'));
  assert.ok(committeeEditHtml.includes('إلغاء التعديل'));
  assert.ok(committeeEditHtml.includes('value="عضو أول"'));

  const postEditHtml = renderToStaticMarkup(
    <PostsAdminPanel
      posts={[{ id: 2, title: 'عنوان قديم', summary: 'ملخص', category: 'general' }]}
      initialEditingItem={{ id: 2, title: 'عنوان قديم', summary: 'ملخص', category: 'general' }}
    />
  );
  assert.ok(postEditHtml.includes('حفظ التعديلات'));
  assert.ok(postEditHtml.includes('value="عنوان قديم"'));

  const mediaEditHtml = renderToStaticMarkup(
    <MediaLinksAdminPanel
      mediaLinks={[{ id: 3, postId: 2, title: 'رابط', mediaType: 'video', canonicalUrl: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' }]}
      posts={[{ id: 2, title: 'عنوان قديم' }]}
      initialEditingItem={{ id: 3, postId: 2, title: 'رابط', mediaType: 'video', canonicalUrl: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' }}
    />
  );
  assert.ok(mediaEditHtml.includes('حفظ التعديلات'));
  assert.ok(mediaEditHtml.includes('value="https://www.youtube.com/watch?v=dQw4w9WgXcQ"'));

  const formEditHtml = renderToStaticMarkup(
    <FormsAdminPanel
      forms={[{ id: 4, formType: 'feedback', title: 'استمارة', embedUrl: 'https://docs.google.com/forms/d/e/1234567890ab/viewform?embedded=true', active: true }]}
      initialEditingItem={{ id: 4, formType: 'feedback', title: 'استمارة', embedUrl: 'https://docs.google.com/forms/d/e/1234567890ab/viewform?embedded=true', active: true }}
    />
  );
  assert.ok(formEditHtml.includes('حفظ التعديلات'));
  assert.ok(formEditHtml.includes('value="استمارة"'));
});

test('App renders public view with accessible admin entry button and renders protected admin login when initialView="admin"', () => {
  const publicHtml = renderToStaticMarkup(<App />);
  assert.match(publicHtml, /dir="rtl"/);
  assert.ok(publicHtml.includes('لوحة الإدارة'));
  assert.ok(publicHtml.includes('لوحة الإعلانات والفعاليات'));

  const adminHtml = renderToStaticMarkup(<App initialView="admin" />);
  assert.match(adminHtml, /dir="rtl"/);
  assert.ok(adminHtml.includes('تسجيل الدخول إلى لوحة الإدارة'));
  assert.doesNotMatch(adminHtml, /role="tablist"/);
});

test('styles.css defines mobile-first admin layout and responsive desktop breakpoints', () => {
  const cssPath = path.resolve(process.cwd(), 'src/styles.css');
  const cssContent = fs.readFileSync(cssPath, 'utf-8');

  assert.match(cssContent, /\.admin-panel\b/);
  assert.match(cssContent, /\.admin-form__grid\s*\{[^}]*grid-template-columns:\s*1fr/);
  assert.match(
    cssContent,
    /@media\s*\(min-width:\s*640px\)[\s\S]*?\.admin-form__grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*1fr\)/
  );
});

test('AdminDashboard and App keep onDataChanged callback stable to prevent infinite session-bootstrap loops', () => {
  const dashboardSrc = fs.readFileSync(
    path.resolve(process.cwd(), 'src/components/admin/AdminDashboard.jsx'),
    'utf-8'
  );
  const appSrc = fs.readFileSync(
    path.resolve(process.cwd(), 'src/App.jsx'),
    'utf-8'
  );

  assert.match(dashboardSrc, /useRef\(onDataChanged\)/);
  assert.doesNotMatch(dashboardSrc, /\[onDataChanged\]/);
  assert.match(appSrc, /const handleAdminDataChanged = useCallback\(/);
});
