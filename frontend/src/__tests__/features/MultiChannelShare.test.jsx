import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  DEFAULT_FORM_SHARE_TITLE,
  FACEBOOK_SHARE_BASE_URL,
  buildFacebookShareUrl,
  buildFormDeepLink,
  buildFormSharePayload,
  buildSharePayload,
  copyShareLink,
  executeShareButtonAction,
  isMobileDevice,
  parseFormIdFromLocation,
  shouldUseNativeMobileShare,
} from '../../utils/whatsappShare.js';
import ShareActions from '../../components/ShareActions.jsx';
import AnnouncementCard from '../../components/AnnouncementCard.jsx';
import PostDetailView from '../../components/PostDetailView.jsx';
import EngagementSection from '../../components/EngagementSection.jsx';
import GoogleFormEmbed from '../../components/GoogleFormEmbed.jsx';
import App from '../../App.jsx';

const samplePost = {
  id: 102,
  title: 'يوم التراث والهوية في مدرسة المحجر',
  summary: 'دعوة لأهالي الطلاب للمشاركة في فعاليات يوم التراث السنوي.',
  category: 'upcoming_event',
  publishedAt: '2026-11-24T10:30:00Z',
};

const sampleForms = [
  {
    id: 1,
    formType: 'feedback',
    title: 'نموذج إبداء الرأي والمقترحات العامة',
    description: 'نرحب بآرائكم ومقترحاتكم.',
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
    id: 3,
    formType: 'event_registration',
    title: 'استمارة التسجيل والمشاركة في الفعاليات المدرسية',
    description: 'سجّلوا للمشاركة في الفعاليات القادمة.',
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

// 1. Form deep-link & parsing utilities
test('buildFormDeepLink constructs #form-<id> deep links ignoring external Google Form directUrl', () => {
  assert.equal(
    buildFormDeepLink(sampleForms[1], { baseUrl: 'https://mahjar.example.org' }),
    'https://mahjar.example.org/#form-3'
  );

  assert.equal(
    buildFormDeepLink(
      { id: 3, directUrl: 'https://docs.google.com/forms/d/e/abc/viewform' },
      { baseUrl: 'https://mahjar.example.org/admin?foo=bar#old' }
    ),
    'https://mahjar.example.org/#form-3'
  );

  assert.equal(
    buildFormDeepLink(
      { title: 'نموذج بدون معرف' },
      { baseUrl: 'https://mahjar.example.org' }
    ),
    'https://mahjar.example.org/#engagement-section'
  );

  assert.equal(
    buildFormDeepLink({ id: 3 }),
    '/#form-3',
    'Should fall back to root-relative #form-<id> when neither baseUrl nor window.location exists'
  );
});

test('parseFormIdFromLocation extracts form IDs from hashes, URLs, and query strings while ignoring unrelated/malformed inputs', () => {
  assert.equal(parseFormIdFromLocation('#form-3'), '3');
  assert.equal(
    parseFormIdFromLocation('https://mahjar.example.org/#form-3'),
    '3'
  );
  assert.equal(
    parseFormIdFromLocation({ hash: '#form-9', search: '' }),
    '9'
  );
  assert.equal(
    parseFormIdFromLocation({ hash: '', search: '?form=2' }),
    '2'
  );
  assert.equal(
    parseFormIdFromLocation('#form-event%20reg'),
    'event reg'
  );

  for (const invalid of [
    '#post-1',
    '#admin',
    '#engagement-section',
    '',
    null,
    undefined,
    '#form-%E0%A4%A',
    { hash: '', search: '' },
  ]) {
    assert.equal(
      parseFormIdFromLocation(invalid),
      null,
      `Expected null for form location input: ${JSON.stringify(invalid)}`
    );
  }
});

// 2. Multi-channel share URL builders & payloads (without Telegram)
test('buildFacebookShareUrl encodes valid URLs and rejects unsafe schemes', () => {
  const target = 'https://mahjar.example.org/#form-3';
  const fbUrl = buildFacebookShareUrl(target);
  assert.ok(fbUrl.startsWith(`${FACEBOOK_SHARE_BASE_URL}?u=`));
  assert.equal(new URL(fbUrl).searchParams.get('u'), target);

  for (const bad of ['javascript:alert(1)', 'data:text/html,<script>', '']) {
    assert.equal(buildFacebookShareUrl(bad), '');
  }
});

test('buildSharePayload and buildFormSharePayload build WhatsApp, Facebook, and Email share URLs without Telegram', () => {
  const postPayload = buildSharePayload(samplePost, {
    baseUrl: 'https://mahjar.example.org',
  });
  assert.ok(postPayload);
  assert.equal(postPayload.url, 'https://mahjar.example.org/#post-102');
  assert.ok(postPayload.whatsappUrl.startsWith('https://wa.me/?text='));
  assert.equal(
    new URL(postPayload.facebookUrl).searchParams.get('u'),
    'https://mahjar.example.org/#post-102'
  );
  assert.ok(postPayload.emailUrl.startsWith('mailto:?subject='));
  assert.equal('telegramUrl' in postPayload, false);

  const formPayload = buildFormSharePayload(sampleForms[1], {
    baseUrl: 'https://mahjar.example.org',
  });
  assert.ok(formPayload);
  assert.equal(
    formPayload.title,
    'استمارة التسجيل والمشاركة في الفعاليات المدرسية'
  );
  assert.equal(formPayload.url, 'https://mahjar.example.org/#form-3');
  assert.ok(
    decodeURIComponent(formPayload.whatsappUrl).includes('#form-3'),
    'WhatsApp share text for form must include #form-<id>'
  );
  assert.equal(
    new URL(formPayload.facebookUrl).searchParams.get('u'),
    'https://mahjar.example.org/#form-3'
  );
  assert.equal('telegramUrl' in formPayload, false);

  const fallbackFormPayload = buildFormSharePayload(
    { id: 8, title: '<script>alert(1)</script>' },
    { baseUrl: 'https://mahjar.example.org' }
  );
  assert.equal(fallbackFormPayload.title, DEFAULT_FORM_SHARE_TITLE);
});

// 2b. Mobile native share behavior
test('isMobileDevice, shouldUseNativeMobileShare, and executeShareButtonAction invoke Web Share API on mobile devices and open menu on desktop or fallback', async () => {
  const androidNav = {
    userAgent:
      'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Mobile Safari/537.36',
    share: async () => {},
  };
  const iphoneNav = {
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
    share: async () => {},
  };
  const uaDataMobileNav = {
    userAgent: 'CustomBrowser',
    userAgentData: { mobile: true },
    share: async () => {},
  };
  const desktopNavWithShare = {
    userAgent:
      'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    share: async () => {},
  };
  const coarsePointerWindow = {
    matchMedia: (q) => ({ matches: q === '(pointer: coarse)' }),
  };

  assert.equal(isMobileDevice(androidNav), true);
  assert.equal(isMobileDevice(iphoneNav), true);
  assert.equal(isMobileDevice(uaDataMobileNav), true);
  assert.equal(isMobileDevice({ userAgent: 'Desktop' }, coarsePointerWindow), true);
  assert.equal(isMobileDevice(desktopNavWithShare, { matchMedia: () => ({ matches: false }) }), false);

  assert.equal(
    shouldUseNativeMobileShare({
      navigatorObj: androidNav,
      shareData: { title: 't', url: 'https://mahjar.example.org/#post-102' },
    }),
    true
  );
  assert.equal(
    shouldUseNativeMobileShare({
      navigatorObj: desktopNavWithShare,
      windowObj: { matchMedia: () => ({ matches: false }) },
      shareData: { title: 't', url: 'https://mahjar.example.org/#post-102' },
    }),
    false
  );

  // Mobile working navigator.share -> invokes native share sheet directly
  const mobileCalls = [];
  const mobileRes = await executeShareButtonAction(samplePost, {
    baseUrl: 'https://mahjar.example.org',
    navigatorObj: {
      ...androidNav,
      share: async (data) => {
        mobileCalls.push(data);
      },
    },
  });
  assert.equal(mobileRes.action, 'native-shared');
  assert.equal(mobileRes.method, 'web-share');
  assert.equal(mobileRes.status, 'shared');
  assert.deepEqual(mobileCalls, [
    {
      title: samplePost.title,
      text: samplePost.title,
      url: 'https://mahjar.example.org/#post-102',
    },
  ]);

  // Mobile user cancels native share sheet (AbortError) -> cancelled without forcing fallback menu
  const cancelRes = await executeShareButtonAction(samplePost, {
    baseUrl: 'https://mahjar.example.org',
    navigatorObj: {
      ...iphoneNav,
      share: async () => {
        const err = new Error('Cancelled');
        err.name = 'AbortError';
        throw err;
      },
    },
  });
  assert.equal(cancelRes.action, 'cancelled');
  assert.equal(cancelRes.method, 'web-share');
  assert.equal(cancelRes.status, 'cancelled');

  // Mobile native share errors (non-AbortError) -> falls back to opening menu
  const errorRes = await executeShareButtonAction(sampleForms[1], {
    entityType: 'form',
    baseUrl: 'https://mahjar.example.org',
    navigatorObj: {
      ...androidNav,
      share: async () => {
        throw new Error('NotAllowedError');
      },
    },
  });
  assert.equal(errorRes.action, 'open-menu');
  assert.equal(errorRes.method, 'menu');
  assert.equal(errorRes.status, 'fallback');
  assert.equal(errorRes.payload.url, 'https://mahjar.example.org/#form-3');

  // Desktop browser -> toggles menu directly without calling navigator.share
  const desktopCalls = [];
  const desktopRes = await executeShareButtonAction(samplePost, {
    baseUrl: 'https://mahjar.example.org',
    navigatorObj: {
      ...desktopNavWithShare,
      share: async (data) => {
        desktopCalls.push(data);
      },
    },
    windowObj: { matchMedia: () => ({ matches: false }) },
  });
  assert.equal(desktopRes.action, 'open-menu');
  assert.equal(desktopRes.method, 'menu');
  assert.equal(desktopRes.status, 'toggle');
  assert.equal(desktopCalls.length, 0);
});

// 3. Clipboard copy helper
test('copyShareLink uses Clipboard API, falls back to execCommand, and handles invalid/failing cases safely', async () => {
  const copiedValues = [];
  const res1 = await copyShareLink('https://mahjar.example.org/#form-3', {
    clipboardObj: {
      writeText: async (val) => {
        copiedValues.push(val);
      },
    },
  });
  assert.deepEqual(res1, { copied: true, method: 'clipboard' });
  assert.deepEqual(copiedValues, ['https://mahjar.example.org/#form-3']);

  // Fallback to execCommand when clipboard API fails
  let appendedNode = null;
  let removedNode = null;
  const mockDoc = {
    body: {
      appendChild: (node) => {
        appendedNode = node;
      },
      removeChild: (node) => {
        removedNode = node;
      },
    },
    createElement: () => ({
      value: '',
      style: {},
      setAttribute: () => {},
      select: () => {},
    }),
    execCommand: (cmd) => cmd === 'copy',
  };

  const res2 = await copyShareLink('https://mahjar.example.org/#post-102', {
    clipboardObj: {
      writeText: async () => {
        throw new Error('NotAllowedError');
      },
    },
    documentObj: mockDoc,
  });
  assert.deepEqual(res2, { copied: true, method: 'execCommand' });
  assert.ok(appendedNode && removedNode && appendedNode === removedNode);

  assert.deepEqual(await copyShareLink('javascript:alert(1)'), {
    copied: false,
    method: 'none',
  });
  assert.deepEqual(await copyShareLink(''), {
    copied: false,
    method: 'none',
  });

  const resFail = await copyShareLink('https://mahjar.example.org/#post-1', {
    clipboardObj: null,
    documentObj: null,
  });
  assert.deepEqual(resFail, { copied: false, method: 'failed' });
});

// 4. ShareActions component
test('ShareActions renders a single Share button when closed and opens a menu with WhatsApp, Facebook, and Copy Link (no Telegram)', () => {
  const closedHtml = renderToStaticMarkup(
    <ShareActions
      item={samplePost}
      entityType="post"
      baseUrl="https://mahjar.example.org"
    />
  );

  const closedButtons = closedHtml.match(/<button\b/g) ?? [];
  assert.equal(closedButtons.length, 1, 'Closed ShareActions must render exactly 1 button');
  assert.doesNotMatch(
    closedHtml,
    /<a\b/,
    'Closed ShareActions must not render external share links outside the menu'
  );
  assert.doesNotMatch(
    closedHtml,
    /مشاركة عبر واتساب/,
    'Closed ShareActions must not render a duplicate standalone WhatsApp button'
  );
  assert.match(closedHtml, /aria-haspopup="menu"/);
  assert.match(closedHtml, /aria-expanded="false"/);
  assert.match(
    closedHtml,
    /data-share-url="https:\/\/mahjar\.example\.org\/#post-102"/
  );
  assert.match(closedHtml, /data-whatsapp-url="https:\/\/wa\.me\/\?text=[^"]+"/);
  assert.ok(closedHtml.includes('مشاركة'));
  assert.doesNotMatch(closedHtml, /role="menu"/);
  assert.doesNotMatch(closedHtml, /<img\b/);
  assert.match(closedHtml, /min-height:\s*44px/);
  assert.match(closedHtml, /min-width:\s*44px/);

  for (const { item, entityType, expectedHash } of [
    { item: samplePost, entityType: 'post', expectedHash: '#post-102' },
    { item: sampleForms[1], entityType: 'form', expectedHash: '#form-3' },
  ]) {
    const openHtml = renderToStaticMarkup(
      <ShareActions
        item={item}
        entityType={entityType}
        baseUrl="https://mahjar.example.org"
        initialMenuOpen={true}
      />
    );

    assert.match(openHtml, /aria-expanded="true"/);
    assert.match(openHtml, /role="menu"/);
    const menuItems = openHtml.match(/role="menuitem"/g) ?? [];
    assert.equal(
      menuItems.length,
      3,
      'Share menu must contain exactly 3 items: WhatsApp, Facebook, Copy Link'
    );
    assert.match(
      openHtml,
      /href="https:\/\/wa\.me\/\?text=[^"]+"[^>]*target="_blank"[^>]*rel="noopener noreferrer"/
    );
    assert.ok(openHtml.includes('مشاركة عبر واتساب'));
    assert.match(
      openHtml,
      new RegExp(
        `href="https://www\\.facebook\\.com/sharer/sharer\\.php\\?u=[^"]*${expectedHash.slice(1)}"[^>]*target="_blank"[^>]*rel="noopener noreferrer"`
      )
    );
    assert.ok(openHtml.includes('مشاركة عبر فيسبوك'));
    assert.ok(openHtml.includes('نسخ الرابط'));
    assert.ok(!openHtml.includes('تيليغرام'), 'Telegram must be removed');
    assert.ok(!openHtml.includes('t.me/share'), 'Telegram URL must be removed');
    assert.ok(
      !openHtml.includes('مشاركة عبر تطبيقات الجهاز'),
      'Native share is triggered directly on mobile trigger click rather than listed inside menu'
    );

    const waPos = openHtml.indexOf('مشاركة عبر واتساب');
    const fbPos = openHtml.indexOf('مشاركة عبر فيسبوك');
    const copyPos = openHtml.indexOf('نسخ الرابط');
    assert.ok(
      waPos !== -1 && waPos < fbPos && fbPos < copyPos,
      'WhatsApp must appear first inside the Share menu, followed by Facebook and Copy Link'
    );
    assert.doesNotMatch(openHtml, /<img\b/);
  }

  assert.equal(renderToStaticMarkup(<ShareActions item={null} />), '');
});

// 5. Integration across Announcements, EngagementSection, GoogleFormEmbed, and App
test('AnnouncementCard and PostDetailView render a single unified Share menu button', () => {
  const cardHtml = renderToStaticMarkup(
    <AnnouncementCard post={samplePost} shareBaseUrl="https://mahjar.example.org" />
  );
  assert.equal((cardHtml.match(/aria-haspopup="menu"/g) ?? []).length, 1);
  assert.ok(!cardHtml.includes('مشاركة عبر واتساب'));
  assert.match(cardHtml, /data-whatsapp-url="https:\/\/wa\.me\/\?text=[^"]+"/);

  const detailHtml = renderToStaticMarkup(
    <PostDetailView
      post={samplePost}
      shareBaseUrl="https://mahjar.example.org"
      onClose={() => {}}
    />
  );
  assert.equal((detailHtml.match(/aria-haspopup="menu"/g) ?? []).length, 1);
  assert.ok(!detailHtml.includes('مشاركة عبر واتساب'));
  assert.match(detailHtml, /data-whatsapp-url="https:\/\/wa\.me\/\?text=[^"]+"/);
});

test('EngagementSection and GoogleFormEmbed expose #form-<id> deep links via a single ShareActions trigger without overriding direct Google Form links', () => {
  const defaultSectionHtml = renderToStaticMarkup(
    <EngagementSection
      forms={sampleForms}
      shareBaseUrl="https://mahjar.example.org"
    />
  );

  assert.match(defaultSectionHtml, /id="form-1"/);
  assert.match(defaultSectionHtml, /id="form-3"/);
  assert.ok(!defaultSectionHtml.includes('مشاركة عبر واتساب'));
  assert.doesNotMatch(
    defaultSectionHtml,
    /<iframe\b/,
    'Default EngagementSection must not mount an iframe until a form is chosen'
  );

  const defaultMenuTriggers = defaultSectionHtml.match(/aria-haspopup="menu"/g) ?? [];
  assert.equal(defaultMenuTriggers.length, 2, 'One share trigger per form card when unselected');

  const selectedSectionHtml = renderToStaticMarkup(
    <EngagementSection
      forms={sampleForms}
      initialSelectedFormId={3}
      shareBaseUrl="https://mahjar.example.org"
    />
  );

  const menuTriggerMatches = selectedSectionHtml.match(/aria-haspopup="menu"/g) ?? [];
  assert.equal(menuTriggerMatches.length, 3, 'Two card share triggers plus one in selected embed below');

  const waAttrMatches = [
    ...selectedSectionHtml.matchAll(/data-whatsapp-url="(https:\/\/wa\.me\/\?text=[^"]+)"/g),
  ];
  assert.equal(waAttrMatches.length, 3);
  for (const match of waAttrMatches) {
    const decoded = decodeURIComponent(match[1]);
    assert.match(
      decoded,
      /#form-(1|3)/,
      'Engagement form WhatsApp share URLs must point to #form-<id> deep link'
    );
    assert.ok(
      !decoded.includes('docs.google.com'),
      'Engagement form WhatsApp share URL must share platform deep link, not raw Google Forms URL'
    );
  }

  const embedHtml = renderToStaticMarkup(
    <GoogleFormEmbed
      form={sampleForms[1]}
      shareBaseUrl="https://mahjar.example.org"
    />
  );
  assert.equal((embedHtml.match(/aria-haspopup="menu"/g) ?? []).length, 1);
  assert.match(embedHtml, /data-whatsapp-url="https:\/\/wa\.me\/\?text=[^"]+"/);
  assert.ok(
    embedHtml.includes(`href="${sampleForms[1].directUrl}"`),
    'GoogleFormEmbed must preserve bottom direct Google Forms link'
  );
  assert.ok(
    embedHtml.includes('الانتقال المباشر للنموذج'),
    'GoogleFormEmbed must preserve bottom الانتقال المباشر للنموذج button'
  );
  assert.ok(
    !embedHtml.includes('فتح النموذج في نافذة جديدة'),
    'GoogleFormEmbed must not render top فتح النموذج في نافذة جديدة link'
  );

  const appHtml = renderToStaticMarkup(<App />);
  assert.match(appHtml, /data-whatsapp-url="https:\/\/wa\.me\/\?text=[^"]*post-/);
  const engagementAppHtml = renderToStaticMarkup(<App initialPage="engagement" />);
  assert.match(engagementAppHtml, /data-whatsapp-url="https:\/\/wa\.me\/\?text=[^"]*form-/);
});

// 6. Open Graph & CSS checks
test('index.html defines Open Graph and Twitter Card metadata and styles.css allows popover overflow', () => {
  const indexHtmlPath = path.resolve(process.cwd(), 'index.html');
  const indexHtml = fs.readFileSync(indexHtmlPath, 'utf-8');

  assert.match(indexHtml, /property="og:title"/);
  assert.match(indexHtml, /property="og:description"/);
  assert.match(indexHtml, /property="og:image"/);
  assert.match(indexHtml, /property="og:locale"\s+content="ar_AR"/);
  assert.match(indexHtml, /name="twitter:card"/);

  const cssPath = path.resolve(process.cwd(), 'src/styles.css');
  const cssContent = fs.readFileSync(cssPath, 'utf-8');

  assert.match(
    cssContent,
    /\.share-actions__more-btn\s*\{[^}]*min-height:\s*44px[^}]*min-width:\s*44px/s
  );
  assert.match(
    cssContent,
    /\.share-actions__menu-item\s*\{[^}]*min-height:\s*44px[^}]*min-width:\s*44px/s
  );
  assert.doesNotMatch(
    cssContent,
    /\.announcement-card\s*\{[^}]*overflow:\s*hidden/s,
    '.announcement-card must not clip open share menus with overflow: hidden'
  );
  assert.doesNotMatch(
    cssContent,
    /\.engagement-embed\s*\{[^}]*overflow:\s*hidden/s,
    '.engagement-embed must not clip open share menus with overflow: hidden'
  );
});
