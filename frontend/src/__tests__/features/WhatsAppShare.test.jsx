import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  DEFAULT_SHARE_TITLE,
  WHATSAPP_SHARE_BASE_URL,
  buildPostDeepLink,
  buildSharePayload,
  buildWhatsAppShareUrl,
  canUseWebShare,
  parsePostIdFromLocation,
  sharePost,
} from '../../utils/whatsappShare.js';
import WhatsAppShareButton from '../../components/WhatsAppShareButton.jsx';
import AnnouncementCard from '../../components/AnnouncementCard.jsx';
import AnnouncementsFeed from '../../components/AnnouncementsFeed.jsx';
import PostDetailView from '../../components/PostDetailView.jsx';
import App from '../../App.jsx';

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
    summary: 'دعوة لأهالي الطلاب للمشاركة في فعاليات يوم التراث السنوي.',
    category: 'upcoming_event',
    publishedAt: '2026-11-24T10:30:00Z',
    eventDate: '2026-12-05',
  },
  {
    id: 103,
    title: 'مبادرة أصدقاء المكتبة والقراءة الحرة',
    summary: 'انطلاق نشاط القراءة الأسبوعي لطلاب الصفوف الأولى.',
    category: 'student_activity',
    publishedAt: '2026-11-18T12:15:00Z',
  },
  {
    id: 104,
    title: 'مستجدات مشروع تظليل ساحة المدرسة (العريشة)',
    summary: 'استكمال المرحلة الأولى من تركيب العريشة.',
    category: 'updates',
    publishedAt: '2026-11-22T16:45:00Z',
  },
];

function decodeWhatsAppText(whatsappUrl) {
  const parsed = new URL(whatsappUrl);
  return parsed.searchParams.get('text') ?? '';
}

// 1. buildPostDeepLink
test('buildPostDeepLink constructs canonical deep links, normalizes paths, and rejects unsafe explicit URLs', () => {
  assert.equal(
    buildPostDeepLink({ id: 102 }, { baseUrl: 'https://mahjar.example.org' }),
    'https://mahjar.example.org/#post-102'
  );

  assert.equal(
    buildPostDeepLink(
      { id: 102 },
      { baseUrl: 'https://mahjar.example.org/school/?a=1#old' }
    ),
    'https://mahjar.example.org/school/#post-102'
  );

  assert.equal(
    buildPostDeepLink(
      { id: 102 },
      { baseUrl: 'https://mahjar.example.org/admin' }
    ),
    'https://mahjar.example.org/#post-102'
  );

  assert.equal(
    buildPostDeepLink(
      { id: 55, directUrl: 'https://mahjar.example.org/posts/55' },
      { baseUrl: 'https://fallback.example.org' }
    ),
    'https://mahjar.example.org/posts/55'
  );
  assert.equal(
    buildPostDeepLink(
      { id: 56, direct_url: 'https://mahjar.example.org/posts/56' },
      { baseUrl: 'https://fallback.example.org' }
    ),
    'https://mahjar.example.org/posts/56'
  );
  assert.equal(
    buildPostDeepLink(
      { id: 57, shareUrl: 'https://mahjar.example.org/share/57' },
      { baseUrl: 'https://fallback.example.org' }
    ),
    'https://mahjar.example.org/share/57'
  );
  assert.equal(
    buildPostDeepLink(
      { id: 58, share_url: 'https://mahjar.example.org/share/58' },
      { baseUrl: 'https://fallback.example.org' }
    ),
    'https://mahjar.example.org/share/58'
  );

  for (const unsafeUrl of [
    'javascript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'https://user:pass@evil.com/phish',
  ]) {
    assert.equal(
      buildPostDeepLink(
        { id: 102, directUrl: unsafeUrl },
        { baseUrl: 'https://mahjar.example.org' }
      ),
      'https://mahjar.example.org/#post-102',
      `Must reject unsafe explicit URL: ${unsafeUrl}`
    );
  }

  assert.equal(
    buildPostDeepLink({ title: 'إعلان بدون معرف' }, { baseUrl: 'https://mahjar.example.org' }),
    'https://mahjar.example.org/#announcements-feed'
  );

  assert.equal(
    buildPostDeepLink({ id: 102 }),
    '/#post-102',
    'Should fall back to root-relative #post-<id> when neither baseUrl nor window.location exists'
  );

  assert.equal(
    buildPostDeepLink(
      { id: 'event 2026/1&a=b' },
      { baseUrl: 'https://mahjar.example.org' }
    ),
    'https://mahjar.example.org/#post-event%202026%2F1%26a%3Db'
  );
});

// 2. parsePostIdFromLocation
test('parsePostIdFromLocation extracts post IDs from hashes, URLs, and query strings while ignoring unrelated/malformed inputs', () => {
  assert.equal(parsePostIdFromLocation('#post-102'), '102');
  assert.equal(
    parsePostIdFromLocation('https://mahjar.example.org/#post-102'),
    '102'
  );
  assert.equal(
    parsePostIdFromLocation({ hash: '#post-42', search: '' }),
    '42'
  );
  assert.equal(
    parsePostIdFromLocation({ hash: '', search: '?post=77' }),
    '77'
  );
  assert.equal(
    parsePostIdFromLocation('#post-event%202026'),
    'event 2026'
  );

  for (const invalid of [
    '#admin',
    '#engagement-section',
    '',
    null,
    undefined,
    '#post-%E0%A4%A',
    { hash: '', search: '' },
  ]) {
    assert.equal(
      parsePostIdFromLocation(invalid),
      null,
      `Expected null for location input: ${JSON.stringify(invalid)}`
    );
  }
});

// 3. buildSharePayload & buildWhatsAppShareUrl
test('buildSharePayload and buildWhatsAppShareUrl encode title and deep link safely and strip XSS', () => {
  const payload = buildSharePayload(samplePosts[1], {
    baseUrl: 'https://mahjar.example.org',
  });
  assert.ok(payload);
  assert.equal(payload.title, 'يوم التراث والهوية في مدرسة المحجر');
  assert.equal(payload.url, 'https://mahjar.example.org/#post-102');
  assert.equal(
    payload.text,
    'يوم التراث والهوية في مدرسة المحجر\nhttps://mahjar.example.org/#post-102'
  );
  assert.ok(payload.whatsappUrl.startsWith(`${WHATSAPP_SHARE_BASE_URL}?text=`));
  assert.equal(decodeWhatsAppText(payload.whatsappUrl), payload.text);

  const waUrl = buildWhatsAppShareUrl(samplePosts[1], {
    baseUrl: 'https://mahjar.example.org',
  });
  assert.equal(waUrl, payload.whatsappUrl);

  const specialPost = {
    id: 205,
    title: 'سؤال & جواب #مهم = للأهالي؟',
  };
  const specialWaUrl = buildWhatsAppShareUrl(specialPost, {
    baseUrl: 'https://mahjar.example.org',
  });
  assert.equal(
    decodeWhatsAppText(specialWaUrl),
    'سؤال & جواب #مهم = للأهالي؟\nhttps://mahjar.example.org/#post-205'
  );

  const xssPost = {
    id: 300,
    title: '<script>alert(1)</script><b>إعلان</b> javascript:alert(1) هام',
  };
  const xssPayload = buildSharePayload(xssPost, {
    baseUrl: 'https://mahjar.example.org',
  });
  assert.ok(!xssPayload.title.includes('<script>'));
  assert.ok(!xssPayload.title.includes('<b>'));
  assert.ok(!xssPayload.title.toLowerCase().includes('javascript:'));
  assert.ok(xssPayload.title.includes('إعلان'));
  assert.ok(xssPayload.title.includes('هام'));

  const emptyTitlePayload = buildSharePayload(
    { id: 301, title: '<script>alert(1)</script>' },
    { baseUrl: 'https://mahjar.example.org' }
  );
  assert.equal(emptyTitlePayload.title, DEFAULT_SHARE_TITLE);

  assert.equal(buildSharePayload(null), null);
  assert.equal(buildSharePayload(undefined), null);
  assert.equal(buildWhatsAppShareUrl(null), '');
});

// 4. canUseWebShare & sharePost
test('canUseWebShare and sharePost support Web Share API, AbortError handling, and WhatsApp URL fallback', async () => {
  const shareCalls = [];
  const workingNav = {
    share: async (data) => {
      shareCalls.push(data);
    },
  };
  assert.equal(canUseWebShare(workingNav, { title: 'x', url: 'https://a.com' }), true);
  assert.equal(canUseWebShare(null, { title: 'x' }), false);
  assert.equal(
    canUseWebShare(
      { share: async () => {}, canShare: () => false },
      { title: 'x' }
    ),
    false
  );
  assert.equal(
    canUseWebShare(
      {
        share: async () => {},
        canShare: () => {
          throw new Error('unsupported');
        },
      },
      { title: 'x' }
    ),
    false
  );

  const webShareRes = await sharePost(samplePosts[1], {
    baseUrl: 'https://mahjar.example.org',
    preferWebShare: true,
    navigatorObj: workingNav,
  });
  assert.equal(webShareRes.method, 'web-share');
  assert.equal(webShareRes.status, 'shared');
  assert.equal(shareCalls.length, 1);
  assert.deepEqual(shareCalls[0], {
    title: 'يوم التراث والهوية في مدرسة المحجر',
    text: 'يوم التراث والهوية في مدرسة المحجر',
    url: 'https://mahjar.example.org/#post-102',
  });

  // AbortError must not open fallback window
  const abortOpenCalls = [];
  const abortNav = {
    share: async () => {
      const err = new Error('User cancelled');
      err.name = 'AbortError';
      throw err;
    },
  };
  const abortRes = await sharePost(samplePosts[1], {
    baseUrl: 'https://mahjar.example.org',
    preferWebShare: true,
    navigatorObj: abortNav,
    openWindow: (...args) => {
      abortOpenCalls.push(args);
      return {};
    },
  });
  assert.equal(abortRes.method, 'web-share');
  assert.equal(abortRes.status, 'cancelled');
  assert.equal(abortOpenCalls.length, 0);

  // Non-abort error falls back to openWindow
  const fallbackOpenCalls = [];
  const errorNav = {
    share: async () => {
      throw new Error('NotAllowedError');
    },
  };
  const errorRes = await sharePost(samplePosts[1], {
    baseUrl: 'https://mahjar.example.org',
    preferWebShare: true,
    navigatorObj: errorNav,
    openWindow: (...args) => {
      fallbackOpenCalls.push(args);
      return {};
    },
  });
  assert.equal(errorRes.method, 'whatsapp');
  assert.equal(errorRes.status, 'opened');
  assert.equal(fallbackOpenCalls.length, 1);
  assert.ok(fallbackOpenCalls[0][0].startsWith('https://wa.me/?text='));
  assert.equal(fallbackOpenCalls[0][1], '_blank');
  assert.equal(fallbackOpenCalls[0][2], 'noopener,noreferrer');

  // Default mode (preferWebShare: false): opens WhatsApp; falls back to Web Share if popup blocked
  const defaultOpenCalls = [];
  const defaultRes = await sharePost(samplePosts[0], {
    baseUrl: 'https://mahjar.example.org',
    navigatorObj: workingNav,
    openWindow: (...args) => {
      defaultOpenCalls.push(args);
      return {};
    },
  });
  assert.equal(defaultRes.method, 'whatsapp');
  assert.equal(defaultRes.status, 'opened');
  assert.equal(defaultOpenCalls.length, 1);

  const blockedShareCalls = [];
  const blockedRes = await sharePost(samplePosts[0], {
    baseUrl: 'https://mahjar.example.org',
    navigatorObj: {
      share: async (data) => {
        blockedShareCalls.push(data);
      },
    },
    openWindow: () => null,
  });
  assert.equal(blockedRes.method, 'web-share');
  assert.equal(blockedRes.status, 'shared');
  assert.equal(blockedShareCalls.length, 1);

  // Invalid post
  const invalidRes = await sharePost(null);
  assert.deepEqual(invalidRes, {
    method: 'none',
    status: 'invalid',
    payload: null,
  });
});

// 5. WhatsAppShareButton component
test('WhatsAppShareButton renders accessible RTL WhatsApp share link with inline SVG and 44x44 touch targets', () => {
  const html = renderToStaticMarkup(
    <WhatsAppShareButton
      post={samplePosts[1]}
      baseUrl="https://mahjar.example.org"
    />
  );

  assert.match(html, /<a\b[^>]*dir="rtl"/);
  assert.match(html, /href="https:\/\/wa\.me\/\?text=[^"]+"/);
  assert.match(html, /target="_blank"/);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.match(html, /min-height:\s*44px/);
  assert.match(html, /min-width:\s*44px/);
  assert.ok(html.includes('مشاركة عبر واتساب'));
  assert.match(
    html,
    /aria-label="[^"]*يوم التراث والهوية في مدرسة المحجر[^"]*"/
  );
  assert.match(html, /<svg\b[^>]*aria-hidden="true"/);
  assert.doesNotMatch(html, /<img\b/);

  const hrefMatch = html.match(/href="([^"]+)"/);
  assert.ok(hrefMatch);
  const decodedHref = hrefMatch[1].replace(/&amp;/g, '&');
  const decodedText = decodeWhatsAppText(decodedHref);
  assert.ok(decodedText.includes('يوم التراث والهوية في مدرسة المحجر'));
  assert.ok(decodedText.includes('https://mahjar.example.org/#post-102'));

  assert.equal(renderToStaticMarkup(<WhatsAppShareButton post={null} />), '');
  assert.equal(
    renderToStaticMarkup(<WhatsAppShareButton post={undefined} />),
    ''
  );
});

// 6. Component integration
test('AnnouncementCard renders single Share action across all 4 categories even without onSelectPost and sets post id', () => {
  for (const post of samplePosts) {
    const html = renderToStaticMarkup(
      <AnnouncementCard
        post={post}
        shareBaseUrl="https://mahjar.example.org"
      />
    );
    assert.match(html, new RegExp(`id="post-${post.id}"`));
    assert.match(html, /aria-haspopup="menu"/);
    assert.match(html, /aria-expanded="false"/);
    assert.match(
      html,
      new RegExp(`data-share-url="https://mahjar\\.example\\.org/#post-${post.id}"`)
    );
    assert.match(html, /data-whatsapp-url="https:\/\/wa\.me\/\?text=[^"]+"/);
    assert.ok(html.includes('مشاركة'));
    assert.ok(
      !html.includes('مشاركة عبر واتساب'),
      'Closed card must show only a single unified share button'
    );
    assert.doesNotMatch(html, /<img\b/);
    assert.doesNotMatch(html, /<iframe\b/);
  }
});

test('PostDetailView, AnnouncementsFeed, and App integrate unified Share action and deep-link anchor IDs', () => {
  const detailHtml = renderToStaticMarkup(
    <PostDetailView
      post={samplePosts[1]}
      shareBaseUrl="https://mahjar.example.org"
      onClose={() => {}}
    />
  );
  assert.match(detailHtml, /aria-haspopup="menu"/);
  assert.match(detailHtml, /data-whatsapp-url="https:\/\/wa\.me\/\?text=[^"]+"/);
  assert.ok(detailHtml.includes('العودة إلى قائمة الإعلانات'));

  const feedHtml = renderToStaticMarkup(
    <AnnouncementsFeed
      posts={samplePosts}
      shareBaseUrl="https://mahjar.example.org"
    />
  );
  assert.match(feedHtml, /<section[^>]+id="announcements-feed"/);
  const shareTriggers = feedHtml.match(/aria-haspopup="menu"/g) ?? [];
  assert.equal(
    shareTriggers.length,
    samplePosts.length,
    'Every post card in AnnouncementsFeed must include a unified Share menu button'
  );

  const appHtml = renderToStaticMarkup(<App />);
  assert.match(appHtml, /aria-haspopup="menu"/);
  assert.match(appHtml, /data-whatsapp-url="https:\/\/wa\.me\/\?text=/);
});

// 7. styles.css
test('styles.css defines accessible touch target sizing for .whatsapp-share-btn and .announcement-card__actions', () => {
  const cssPath = path.resolve(process.cwd(), 'src/styles.css');
  const cssContent = fs.readFileSync(cssPath, 'utf-8');

  assert.match(
    cssContent,
    /\.announcement-card__actions\s*\{/,
    'styles.css must define .announcement-card__actions'
  );
  assert.match(
    cssContent,
    /\.whatsapp-share-btn\s*\{[^}]*min-height:\s*44px[^}]*min-width:\s*44px/s,
    '.whatsapp-share-btn must define >= 44x44px touch targets'
  );
});
