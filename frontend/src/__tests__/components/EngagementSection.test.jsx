import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  ENGAGEMENT_FORM_TYPES,
  fetchPublicEngagementForms,
  normalizeAndFilterEngagementForms,
  normalizeEngagementForm,
} from '../../utils/engagementForms.js';
import GoogleFormEmbed from '../../components/GoogleFormEmbed.jsx';
import EngagementSection, {
  isCardActivationKey,
  resolveSelectedEngagementForm,
} from '../../components/EngagementSection.jsx';
import App, { resolvePageFromHash } from '../../App.jsx';

const sampleForms = [
  {
    id: 1,
    formType: 'feedback',
    title: 'نموذج إبداء الرأي والمقترحات العامة',
    description: 'نرحب بآرائكم ومقترحاتكم لتطوير البيئة التعليمية والأنشطة المدرسية.',
    embedUrl:
      'https://docs.google.com/forms/d/e/1FAIpQLScMahjarFeedbackDefault01/viewform?embedded=true',
    canonicalUrl:
      'https://docs.google.com/forms/d/e/1FAIpQLScMahjarFeedbackDefault01/viewform',
    directUrl:
      'https://docs.google.com/forms/d/e/1FAIpQLScMahjarFeedbackDefault01/viewform',
    provider: 'google_forms',
    formId: '1FAIpQLScMahjarFeedbackDefault01',
    active: true,
    displayOrder: 1,
  },
  {
    id: 2,
    formType: 'help_request',
    title: 'نموذج طرح مشكلة عامة أو طلب مساعدة',
    description: 'لتقديم الملاحظات العامة حول محيط المدرسة أو طلب مساندة من اللجنة.',
    embedUrl:
      'https://docs.google.com/forms/d/e/1FAIpQLScMahjarHelpRequestDefault02/viewform?embedded=true',
    canonicalUrl:
      'https://docs.google.com/forms/d/e/1FAIpQLScMahjarHelpRequestDefault02/viewform',
    directUrl:
      'https://docs.google.com/forms/d/e/1FAIpQLScMahjarHelpRequestDefault02/viewform',
    provider: 'google_forms',
    formId: '1FAIpQLScMahjarHelpRequestDefault02',
    active: true,
    displayOrder: 2,
  },
  {
    id: 3,
    formType: 'event_registration',
    title: 'استمارة التسجيل والمشاركة في الفعاليات المدرسية',
    description: 'سجّلوا للمشاركة أو التطوع في الفعاليات والأنشطة القادمة للمدرسة.',
    embedUrl:
      'https://docs.google.com/forms/d/e/1FAIpQLScMahjarEventRegDefault03/viewform?embedded=true',
    canonicalUrl:
      'https://docs.google.com/forms/d/e/1FAIpQLScMahjarEventRegDefault03/viewform',
    directUrl:
      'https://docs.google.com/forms/d/e/1FAIpQLScMahjarEventRegDefault03/viewform',
    provider: 'google_forms',
    formId: '1FAIpQLScMahjarEventRegDefault03',
    active: true,
    displayOrder: 3,
  },
];

// 1. ENGAGEMENT_FORM_TYPES
test('ENGAGEMENT_FORM_TYPES exposes all required form types with Arabic labels', () => {
  const keys = ENGAGEMENT_FORM_TYPES.map((item) => item.id);
  assert.deepEqual(
    keys,
    ['all', 'feedback', 'help_request', 'event_registration'],
    'ENGAGEMENT_FORM_TYPES must expose all and the 3 engagement form types'
  );
  for (const item of ENGAGEMENT_FORM_TYPES) {
    assert.ok(
      typeof item.label === 'string' && item.label.trim().length > 0,
      `Type ${item.id} must define an Arabic label`
    );
  }
});

// 2. normalizeEngagementForm & normalizeAndFilterEngagementForms
test('normalizeEngagementForm normalizes camelCase and snake_case Flask /api/forms payloads and sanitizes XSS/query params', () => {
  const normalized = normalizeEngagementForm({
    id: 55,
    form_type: '  help_request  ',
    title: 'نموذج <script>alert(1)</script> طلب مساعدة',
    description: 'يرجى <img src=x onerror=alert(1)> التعبئة',
    embed_url:
      'https://docs.google.com/forms/u/0/d/e/1FAIpQLScSnakeCaseFormId12345/viewform?usp=sf_link&evil=1&entry.101=الصف+الأول&entry.202=%3Cscript%3Ealert(1)%3C/script%3E',
    display_order: 2,
  });

  assert.ok(normalized, 'Valid snake_case form should normalize cleanly');
  assert.equal(normalized.id, 55);
  assert.equal(normalized.formType, 'help_request');
  assert.equal(normalized.title, 'نموذج طلب مساعدة');
  assert.equal(normalized.description, 'يرجى التعبئة');
  assert.equal(normalized.displayOrder, 2);
  assert.equal(normalized.active, true, 'Omitted active field should default to true');
  assert.equal(normalized.provider, 'google_forms');
  assert.equal(normalized.formId, '1FAIpQLScSnakeCaseFormId12345');
  assert.ok(
    normalized.embedUrl.startsWith(
      'https://docs.google.com/forms/d/e/1FAIpQLScSnakeCaseFormId12345/viewform?embedded=true'
    )
  );
  assert.ok(normalized.embedUrl.includes('entry.101='));
  assert.ok(!normalized.embedUrl.includes('usp='));
  assert.ok(!normalized.embedUrl.includes('evil='));
  assert.ok(!normalized.embedUrl.includes('entry.202='));
  assert.ok(
    normalized.canonicalUrl.startsWith(
      'https://docs.google.com/forms/d/e/1FAIpQLScSnakeCaseFormId12345/viewform?'
    )
  );
  assert.ok(!normalized.canonicalUrl.includes('embedded=true'));
  assert.equal(normalized.directUrl, normalized.canonicalUrl);
});

test('normalizeEngagementForm and GoogleFormEmbed accept shortened https://forms.gle/<id> URLs', () => {
  const shortForm = normalizeEngagementForm({
    id: 77,
    formType: 'feedback',
    title: 'نموذج مختصر للأهالي',
    embedUrl: 'https://forms.gle/fajYrbhcTA3xZa8d9',
    active: true,
  });

  assert.ok(shortForm);
  assert.equal(shortForm.provider, 'google_forms');
  assert.equal(shortForm.formId, 'fajYrbhcTA3xZa8d9');
  assert.equal(shortForm.embedUrl, 'https://forms.gle/fajYrbhcTA3xZa8d9');
  assert.equal(shortForm.canonicalUrl, 'https://forms.gle/fajYrbhcTA3xZa8d9');
  assert.equal(shortForm.directUrl, 'https://forms.gle/fajYrbhcTA3xZa8d9');

  const html = renderToStaticMarkup(<GoogleFormEmbed form={shortForm} />);
  assert.match(
    html,
    /<iframe[^>]+loading="lazy"[^>]+src="https:\/\/forms\.gle\/fajYrbhcTA3xZa8d9"/
  );
  assert.match(
    html,
    /<a[^>]+href="https:\/\/forms\.gle\/fajYrbhcTA3xZa8d9"[^>]+target="_blank"/
  );
});

test('normalizeEngagementForm rejects inactive, untrusted, malformed, unknown-type, and XSS-only forms', () => {
  const rejectedRecords = [
    null,
    undefined,
    { ...sampleForms[0], active: false },
    { ...sampleForms[0], active: null },
    { ...sampleForms[0], active: 'true' },
    { ...sampleForms[0], active: 0 },
    { ...sampleForms[0], formType: 'unknown_kind' },
    { ...sampleForms[0], title: '<script>alert(1)</script>' },
    { ...sampleForms[0], title: '   ' },
    {
      ...sampleForms[0],
      embedUrl: 'https://evil.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform',
    },
    {
      ...sampleForms[0],
      embedUrl:
        'https://docs.google.com.evil.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform',
    },
    {
      ...sampleForms[0],
      embedUrl: 'https://forms.gle.evil.com/fajYrbhcTA3xZa8d9',
    },
    {
      ...sampleForms[0],
      embedUrl: 'http://forms.gle/fajYrbhcTA3xZa8d9',
    },
    {
      ...sampleForms[0],
      embedUrl:
        'http://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform',
    },
    {
      ...sampleForms[0],
      embedUrl: 'javascript:alert(1)',
    },
    {
      ...sampleForms[0],
      embedUrl:
        'https://docs.google.com:8443/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform',
    },
    {
      ...sampleForms[0],
      embedUrl:
        'https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/../../etc/passwd',
    },
    {
      ...sampleForms[0],
      embedUrl: 'https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQr/edit',
    },
  ];

  for (const record of rejectedRecords) {
    assert.equal(
      normalizeEngagementForm(record),
      null,
      `Expected record to be rejected: ${JSON.stringify(record)}`
    );
  }
});

test('normalizeAndFilterEngagementForms orders deterministically, deduplicates by id, and filters by formType', () => {
  const unordered = [
    {
      id: 10,
      formType: 'event_registration',
      title: 'تسجيل بدون ترتيب',
      embedUrl:
        'https://docs.google.com/forms/d/e/1FAIpQLScEventNoOrder12345/viewform',
      displayOrder: null,
    },
    {
      id: 11,
      formType: 'feedback',
      title: 'آراء بدون ترتيب 2',
      embedUrl:
        'https://docs.google.com/forms/d/e/1FAIpQLScFeedbackNoOrder2/viewform',
      displayOrder: null,
    },
    {
      id: 5,
      formType: 'feedback',
      title: 'آراء بدون ترتيب 1',
      embedUrl:
        'https://docs.google.com/forms/d/e/1FAIpQLScFeedbackNoOrder1/viewform',
      displayOrder: null,
    },
    {
      id: 20,
      formType: 'help_request',
      title: 'مساعدة بترتيب 2',
      embedUrl:
        'https://docs.google.com/forms/d/e/1FAIpQLScHelpOrderTwo12345/viewform',
      displayOrder: 2,
    },
    {
      id: 21,
      formType: 'event_registration',
      title: 'تسجيل بترتيب 1',
      embedUrl:
        'https://docs.google.com/forms/d/e/1FAIpQLScEventOrderOne1234/viewform',
      displayOrder: 1,
    },
    {
      id: 21,
      formType: 'event_registration',
      title: 'نسخة مكررة',
      embedUrl:
        'https://docs.google.com/forms/d/e/1FAIpQLScEventOrderOne1234/viewform',
      displayOrder: 1,
    },
  ];

  const orderedAll = normalizeAndFilterEngagementForms(unordered, 'all');
  assert.deepEqual(
    orderedAll.map((item) => item.id),
    [21, 20, 5, 11, 10],
    'Forms must sort by displayOrder asc, then type priority (feedback -> help_request -> event_registration), then numeric id asc'
  );

  const feedbackOnly = normalizeAndFilterEngagementForms(unordered, 'feedback');
  assert.deepEqual(
    feedbackOnly.map((item) => item.id),
    [5, 11]
  );

  const helpOnly = normalizeAndFilterEngagementForms(unordered, 'help_request');
  assert.deepEqual(
    helpOnly.map((item) => item.id),
    [20]
  );

  const eventOnly = normalizeAndFilterEngagementForms(
    unordered,
    'event_registration'
  );
  assert.deepEqual(
    eventOnly.map((item) => item.id),
    [21, 10]
  );
});

// 3. fetchPublicEngagementForms
test('fetchPublicEngagementForms calls /api/forms without Authorization header and normalizes array or envelope payloads', async () => {
  const calls = [];
  const mockFetchArray = async (url, options = {}) => {
    calls.push({ url, options });
    return {
      ok: true,
      status: 200,
      async json() {
        return [
          ...sampleForms,
          {
            id: 99,
            formType: 'feedback',
            title: 'غير مفعل',
            embedUrl:
              'https://docs.google.com/forms/d/e/1FAIpQLScInactiveHidden123/viewform',
            active: false,
          },
        ];
      },
    };
  };

  const forms = await fetchPublicEngagementForms(mockFetchArray);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/forms');
  assert.equal(calls[0].options.method ?? 'GET', 'GET');
  const headers = calls[0].options.headers ?? {};
  assert.equal(
    headers.Authorization ?? headers.authorization,
    undefined,
    'Zero-login public forms fetch must NOT send an Authorization header'
  );
  assert.equal(forms.length, 3);

  const envelopeCalls = [];
  const mockFetchEnvelope = async (url, options = {}) => {
    envelopeCalls.push({ url, options });
    return {
      ok: true,
      status: 200,
      async json() {
        return {
          items: [sampleForms[1]],
          total: 1,
        };
      },
    };
  };

  const filteredForms = await fetchPublicEngagementForms(mockFetchEnvelope, {
    formType: 'help_request',
  });
  assert.equal(envelopeCalls[0].url, '/api/forms?type=help_request');
  assert.equal(filteredForms.length, 1);
  assert.equal(filteredForms[0].formType, 'help_request');

  const failingFetch = async () => ({
    ok: false,
    status: 503,
    async json() {
      return { error: 'Service Unavailable' };
    },
  });

  await assert.rejects(
    () => fetchPublicEngagementForms(failingFetch),
    /503|forms/i
  );
});

// 4. GoogleFormEmbed
test('GoogleFormEmbed renders RTL lazy-loaded Google Forms iframe and keeps only bottom الانتقال المباشر للنموذج link without top new-window button', () => {
  const html = renderToStaticMarkup(<GoogleFormEmbed form={sampleForms[0]} />);

  assert.match(html, /dir="rtl"/, 'GoogleFormEmbed must enforce RTL');
  assert.match(html, /<iframe\b/, 'Must render an iframe element');
  assert.match(
    html,
    /<iframe[^>]+loading="lazy"/,
    'Google Form iframe must include loading="lazy"'
  );
  assert.match(
    html,
    /<iframe[^>]+src="https:\/\/docs\.google\.com\/forms\/d\/e\/1FAIpQLScMahjarFeedbackDefault01\/viewform\?embedded=true"/,
    'Iframe src must use normalized https://docs.google.com/forms/.../viewform?embedded=true URL'
  );
  assert.match(
    html,
    /<iframe[^>]+title="نموذج إبداء الرأي والمقترحات العامة"/,
    'Iframe must expose accessible title'
  );
  assert.match(
    html,
    /referrerpolicy="strict-origin-when-cross-origin"/i,
    'Iframe must enforce strict referrerPolicy'
  );
  assert.match(
    html,
    /sandbox="[^"]*allow-scripts[^"]*allow-forms[^"]*allow-same-origin[^"]*allow-popups[^"]*allow-popups-to-escape-sandbox[^"]*"/,
    'Iframe sandbox must include required Google Forms submission permissions'
  );
  assert.ok(
    !html.includes('فتح النموذج في نافذة جديدة'),
    'GoogleFormEmbed must NOT render "فتح النموذج في نافذة جديدة" button'
  );
  assert.doesNotMatch(
    html,
    /engagement-embed__direct-link/,
    'GoogleFormEmbed must NOT render .engagement-embed__direct-link'
  );
  assert.ok(
    html.includes('الانتقال المباشر للنموذج'),
    'GoogleFormEmbed must keep bottom "الانتقال المباشر للنموذج" button'
  );
  assert.match(
    html,
    /<a[^>]+href="https:\/\/docs\.google\.com\/forms\/d\/e\/1FAIpQLScMahjarFeedbackDefault01\/viewform"[^>]+target="_blank"[^>]+rel="noopener noreferrer"[^>]*class="engagement-embed__fallback-btn"/,
    'Bottom direct fallback button must point to canonical directUrl and open safely in a new tab'
  );
  assert.match(html, /min-height:\s*44px/);
  assert.match(html, /min-width:\s*44px/);
});

test('GoogleFormEmbed returns empty markup with no iframe for untrusted, inactive, or malformed forms', () => {
  const invalidInputs = [
    null,
    undefined,
    { ...sampleForms[0], active: false },
    {
      ...sampleForms[0],
      embedUrl: 'https://evil.com/forms/d/e/1FAIpQLScFakeId123456/viewform',
    },
    { ...sampleForms[0], embedUrl: 'javascript:alert(1)' },
    { ...sampleForms[0], title: '  ' },
  ];

  for (const bad of invalidInputs) {
    const html = renderToStaticMarkup(<GoogleFormEmbed form={bad} />);
    assert.equal(html, '', 'Invalid or inactive form must render empty markup');
    assert.doesNotMatch(html, /<iframe/);
  }
});

// 5. EngagementSection
test('EngagementSection renders RTL zero-login view with NO filter buttons, NO card action buttons, clickable cards, and NO embedded form by default', () => {
  const html = renderToStaticMarkup(<EngagementSection forms={sampleForms} />);

  assert.match(html, /id="engagement-section"/);
  assert.match(html, /dir="rtl"/);
  assert.ok(html.includes('دون الحاجة لإنشاء حساب أو تسجيل دخول'));
  assert.doesNotMatch(
    html,
    /<input[^>]+type="password"/i,
    'Zero-login engagement section must NOT render password or login inputs'
  );

  // Filter-by-type buttons must be completely removed
  assert.doesNotMatch(
    html,
    /role="toolbar"/,
    'EngagementSection must NOT render type filter toolbar'
  );
  assert.doesNotMatch(
    html,
    /engagement-section__filter-btn/,
    'EngagementSection must NOT render type filter buttons'
  );
  assert.ok(!html.includes('>الكل<'), 'Must NOT render "الكل" filter button');

  // All active form cards render cleanly without the removed buttons
  for (const form of sampleForms) {
    assert.ok(html.includes(form.title), `Should render form title: ${form.title}`);
  }
  assert.ok(
    !html.includes('النموذج معروض أدناه'),
    'Must NOT render "النموذج معروض أدناه" button in cards'
  );
  assert.ok(
    !html.includes('تعبئة النموذج هنا'),
    'Must NOT render "تعبئة النموذج هنا" button in cards'
  );
  assert.ok(
    !html.includes('فتح مباشر'),
    'Must NOT render "فتح مباشر" link in cards'
  );
  assert.ok(
    !html.includes('فتح النموذج في نافذة جديدة'),
    'Must NOT render "فتح النموذج في نافذة جديدة" link'
  );
  assert.doesNotMatch(html, /engagement-card__select-btn/);
  assert.doesNotMatch(html, /engagement-card__fallback-link/);
  assert.doesNotMatch(html, /engagement-card__actions/);

  // Each card must be keyboard-focusable and clickable as a whole unit
  const clickableCards = html.match(/engagement-card--clickable/g) ?? [];
  assert.equal(
    clickableCards.length,
    sampleForms.length,
    'Every engagement form card must be clickable across the entire card box'
  );
  const focusableCards = html.match(/<article[^>]+tabindex="0"/gi) ?? [];
  assert.equal(
    focusableCards.length,
    sampleForms.length,
    'Every clickable engagement card must have tabIndex="0" for keyboard accessibility'
  );

  // Default state must NOT display any embedded form until the user chooses one
  assert.doesNotMatch(
    html,
    /<iframe\b/,
    'Default state must NOT mount any iframe before user selects a form'
  );
  assert.doesNotMatch(
    html,
    /engagement-section__embed-stage/,
    'Default state must NOT render the embed stage before user selects a form'
  );
  assert.doesNotMatch(
    html,
    /engagement-card--active/,
    'No card should be marked active in the default unselected state'
  );
});

test('EngagementSection opens selected form below when a form is chosen and keeps bottom الانتقال المباشر للنموذج button', () => {
  assert.equal(resolveSelectedEngagementForm(sampleForms, null), null);
  assert.equal(resolveSelectedEngagementForm(sampleForms, undefined), null);
  assert.equal(resolveSelectedEngagementForm(sampleForms, 999), null);
  assert.equal(resolveSelectedEngagementForm(sampleForms, 2)?.id, 2);

  assert.equal(isCardActivationKey('Enter'), true);
  assert.equal(isCardActivationKey(' '), true);
  assert.equal(isCardActivationKey('Escape'), false);
  assert.equal(isCardActivationKey('Tab'), false);

  const explicitHtml = renderToStaticMarkup(
    <EngagementSection forms={sampleForms} initialSelectedFormId={2} />
  );
  const iframeMatches = explicitHtml.match(/<iframe\b/g) ?? [];
  assert.equal(
    iframeMatches.length,
    1,
    'Selecting a form must mount exactly one lazy-loaded iframe below'
  );
  assert.match(
    explicitHtml,
    /<iframe[^>]+loading="lazy"[^>]+1FAIpQLScMahjarHelpRequestDefault02\/viewform\?embedded=true/
  );
  assert.match(
    explicitHtml,
    /id="form-2"[^>]*class="[^"]*engagement-card--active/,
    'Selected card must receive engagement-card--active highlight'
  );
  assert.ok(
    explicitHtml.includes('الانتقال المباشر للنموذج'),
    'Selected form embed below must keep [الانتقال المباشر للنموذج] button'
  );
  assert.ok(
    !explicitHtml.includes('فتح النموذج في نافذة جديدة'),
    'Selected form embed must NOT include "فتح النموذج في نافذة جديدة"'
  );

  // Verify EngagementSection source attaches click & keyboard activation on the card and stops propagation on Share
  const sectionSrc = fs.readFileSync(
    path.resolve(process.cwd(), 'src/components/EngagementSection.jsx'),
    'utf-8'
  );
  assert.match(
    sectionSrc,
    /<article[\s\S]*?onClick=\{\(\)\s*=>\s*handleSelectForm\(form\)\}/,
    'Whole engagement card <article> must open the form on click'
  );
  assert.match(
    sectionSrc,
    /className="engagement-card__share"[\s\S]*?stopPropagation/,
    'Share wrapper inside card must stop propagation so sharing does not hijack card click'
  );

  const emptyHtml = renderToStaticMarkup(
    <EngagementSection forms={[{ ...sampleForms[0], active: false }]} />
  );
  assert.match(emptyHtml, /dir="rtl"/);
  assert.match(emptyHtml, /role="status"/);
  assert.doesNotMatch(emptyHtml, /<iframe\b/);
});

test('EngagementSection renders cohesive, accessible SVG-based direct contact buttons without raw emojis', () => {
  const members = [
    {
      id: 3,
      fullName: 'طه علي اغباريه',
      role: 'أمين الصندوق ومسؤول التواصل مع الأهالي',
      phone: '0525308582',
      email: 'taha-igbaria@hotmail.com',
      isDirectContact: true,
    },
  ];

  const html = renderToStaticMarkup(
    <EngagementSection forms={sampleForms} members={members} />
  );

  assert.ok(html.includes('تواصل مباشر مع اللجنة'));
  assert.ok(html.includes('طه علي اغباريه'));
  assert.ok(html.includes('أمين الصندوق ومسؤول التواصل مع الأهالي'));

  // All 3 contact channels render with cohesive classes, accessible touch targets, and inline SVG icons
  assert.match(html, /class="[^"]*direct-contact__btn[^"]*direct-contact__btn--phone[^"]*"/);
  assert.match(html, /class="[^"]*direct-contact__btn[^"]*direct-contact__btn--whatsapp[^"]*"/);
  assert.match(html, /class="[^"]*direct-contact__btn[^"]*direct-contact__btn--email[^"]*"/);
  assert.match(html, /href="tel:0525308582"/);
  assert.match(html, /href="https:\/\/wa\.me\/972525308582"/);
  assert.match(html, /href="mailto:taha-igbaria@hotmail\.com"/);

  const iconMatches = html.match(/class="direct-contact__icon"/g) ?? [];
  assert.equal(
    iconMatches.length,
    3,
    'All three direct contact buttons must use crisp inline SVG icons (.direct-contact__icon)'
  );
  assert.doesNotMatch(
    html,
    /[📞💬✉️]/u,
    'Direct contact buttons must NOT use inconsistent raw emoji icons'
  );
});

// 6. App integration
test('App integrates EngagementSection without showing any form by default and resolves #form-<id> deep links to engagement page', () => {
  assert.equal(resolvePageFromHash('#form-2'), 'engagement');
  assert.equal(resolvePageFromHash('#engagement'), 'engagement');
  assert.equal(resolvePageFromHash('#committee'), 'committee');
  assert.equal(resolvePageFromHash('#post-101'), 'announcements');

  const defaultHtml = renderToStaticMarkup(<App initialPage="engagement" />);
  assert.match(defaultHtml, /dir="rtl"/);
  assert.match(defaultHtml, /id="engagement-section"/);
  assert.match(defaultHtml, /href="#announcements"/);
  assert.match(defaultHtml, /href="#engagement"/);
  assert.match(defaultHtml, /href="#committee"/);
  assert.ok(!defaultHtml.includes('id="announcements-feed"'), 'only one page renders at a time');
  assert.ok(!defaultHtml.includes('id="committee-directory-heading"'), 'only one page renders at a time');
  assert.doesNotMatch(
    defaultHtml,
    /<iframe\b/,
    'App on engagement page must NOT display any form iframe by default'
  );
  assert.doesNotMatch(
    defaultHtml,
    /role="toolbar"/,
    'App must NOT render any type filter toolbar'
  );

  const customFormsHtml = renderToStaticMarkup(
    <App
      initialPage="engagement"
      forms={[
        {
          id: 91,
          formType: 'feedback',
          title: 'استبيان أهالي مخصص',
          embedUrl:
            'https://docs.google.com/forms/d/e/1FAIpQLScCustomPublicForm01/viewform?embedded=true',
          active: true,
        },
        {
          id: 92,
          formType: 'help_request',
          title: 'نموذج غير موثوق',
          embedUrl: 'https://evil.com/forms/d/e/1FAIpQLScEvilForm02/viewform',
          active: true,
        },
      ]}
    />
  );
  assert.ok(customFormsHtml.includes('استبيان أهالي مخصص'));
  assert.ok(!customFormsHtml.includes('نموذج غير موثوق'));

  const appSrc = fs.readFileSync(
    path.resolve(process.cwd(), 'src/App.jsx'),
    'utf-8'
  );
  assert.match(appSrc, /fetch\(['"]\/api\/forms['"]\)/);
  assert.match(appSrc, /nextData\?\.forms/);
});

// 7. styles.css responsive layout checks
test('styles.css defines mobile-first grid, desktop breakpoints, and responsive iframe height for engagement view', () => {
  const cssPath = path.resolve(process.cwd(), 'src/styles.css');
  const cssContent = fs.readFileSync(cssPath, 'utf-8');

  assert.match(
    cssContent,
    /\.engagement-section__cards\s*\{[^}]*grid-template-columns:\s*1fr/,
    'Mobile-first default grid for engagement cards must be 1 column'
  );
  assert.match(
    cssContent,
    /@media\s*\(min-width:\s*640px\)[\s\S]*?\.engagement-section__cards\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*1fr\)/,
    'Tablet breakpoint must expand engagement cards grid to 2 columns'
  );
  assert.match(
    cssContent,
    /@media\s*\(min-width:\s*1024px\)[\s\S]*?\.engagement-section__cards\s*\{[^}]*grid-template-columns:\s*repeat\(3,\s*1fr\)/,
    'Desktop breakpoint must expand engagement cards grid to 3 columns'
  );
  assert.match(
    cssContent,
    /\.engagement-embed__iframe\s*\{[^}]*width:\s*100%[^}]*min-height:\s*\d+px/s,
    'Engagement iframe must define responsive 100% width and mobile min-height'
  );
  assert.match(
    cssContent,
    /@media\s*\(min-width:\s*640px\)[\s\S]*?\.engagement-embed__iframe\s*\{[^}]*min-height:\s*\d+px/s,
    'Engagement iframe must define larger desktop min-height at >= 640px'
  );
  assert.match(
    cssContent,
    /\.engagement-card--clickable\s*\{[^}]*cursor:\s*pointer/s,
    'Clickable engagement cards must expose cursor: pointer'
  );
  assert.match(
    cssContent,
    /\.direct-contact__actions\s*\{[^}]*display:\s*grid/s,
    'Direct contact actions must use an aligned equal-width grid layout'
  );
  assert.match(
    cssContent,
    /\.direct-contact__btn\s*\{[^}]*min-height:\s*(?:4[4-9]|[5-9]\d)px/s,
    'Direct contact buttons must enforce accessible >= 44px height in CSS'
  );
});
