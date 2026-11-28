import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import {
  ARABIC_FONT_FAMILIES,
  ARABIC_LANG,
  MIN_TOUCH_TARGET_PX,
  RESPONSIVE_BREAKPOINTS,
  RTL_DIRECTION,
  RTL_ROOT_ATTRIBUTES,
  TOUCH_TARGET_STYLE,
  enforceDocumentRtl,
  resolveViewportTier,
} from '../../utils/rtlLayout.js';
import App from '../../App.jsx';
import AnnouncementCard from '../../components/AnnouncementCard.jsx';
import PostDetailView from '../../components/PostDetailView.jsx';
import EngagementSection from '../../components/EngagementSection.jsx';
import CommitteeAdminPanel from '../../components/admin/CommitteeAdminPanel.jsx';
import LazyMediaImage from '../../components/LazyMediaImage.jsx';
import ShareActions from '../../components/ShareActions.jsx';

const samplePost = {
  id: 102,
  title: 'يوم التراث والهوية في مدرسة المحجر',
  summary: 'دعوة لأهالي الطلاب للمشاركة في فعاليات يوم التراث السنوي.',
  content: 'تفاصيل الفعالية والبرنامج التربوي.',
  category: 'upcoming_event',
  publishedAt: '2026-11-24T10:30:00Z',
};

const sampleForm = {
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
};

// --- 1. rtlLayout utility constants and helpers ---

test('rtlLayout exposes RTL, Arabic font, touch-target, and mobile-first breakpoint constants', () => {
  assert.equal(RTL_DIRECTION, 'rtl');
  assert.equal(ARABIC_LANG, 'ar');
  assert.equal(MIN_TOUCH_TARGET_PX, 44);
  assert.deepEqual(ARABIC_FONT_FAMILIES, ['Tajawal', 'Cairo', 'Noto Sans Arabic']);
  assert.deepEqual(RESPONSIVE_BREAKPOINTS, {
    mobile: 0,
    sm: 640,
    md: 768,
    lg: 1024,
    xl: 1280,
  });
  assert.deepEqual(TOUCH_TARGET_STYLE, {
    minHeight: '44px',
    minWidth: '44px',
  });
  assert.deepEqual(RTL_ROOT_ATTRIBUTES, {
    dir: 'rtl',
    lang: 'ar',
  });
});

test('enforceDocumentRtl forces dir="rtl" and lang="ar" on documentElement and dir="rtl" on body', () => {
  const attrs = new Map([
    ['dir', 'ltr'],
    ['lang', 'en'],
  ]);
  const bodyAttrs = new Map([['dir', 'ltr']]);
  const mockDoc = {
    documentElement: {
      dir: 'ltr',
      lang: 'en',
      setAttribute(name, val) {
        attrs.set(name, val);
      },
    },
    body: {
      dir: 'ltr',
      setAttribute(name, val) {
        bodyAttrs.set(name, val);
      },
    },
  };

  const res = enforceDocumentRtl(mockDoc);
  assert.deepEqual(res, { applied: true, dir: 'rtl', lang: 'ar' });
  assert.equal(mockDoc.documentElement.dir, 'rtl');
  assert.equal(mockDoc.documentElement.lang, 'ar');
  assert.equal(attrs.get('dir'), 'rtl');
  assert.equal(attrs.get('lang'), 'ar');
  assert.equal(mockDoc.body.dir, 'rtl');
  assert.equal(bodyAttrs.get('dir'), 'rtl');

  assert.deepEqual(enforceDocumentRtl(null), {
    applied: false,
    dir: 'rtl',
    lang: 'ar',
  });
  assert.deepEqual(enforceDocumentRtl(undefined), {
    applied: false,
    dir: 'rtl',
    lang: 'ar',
  });
});

test('resolveViewportTier classifies mobile, tablet, and desktop widths deterministically', () => {
  for (const w of [320, 375, 412, 639]) {
    assert.equal(resolveViewportTier(w), 'mobile', `Expected mobile for width=${w}`);
  }
  for (const w of [640, 767]) {
    assert.equal(resolveViewportTier(w), 'sm', `Expected sm for width=${w}`);
  }
  for (const w of [768, 1023]) {
    assert.equal(resolveViewportTier(w), 'md', `Expected md for width=${w}`);
  }
  for (const w of [1024, 1279]) {
    assert.equal(resolveViewportTier(w), 'lg', `Expected lg for width=${w}`);
  }
  for (const w of [1280, 1440]) {
    assert.equal(resolveViewportTier(w), 'xl', `Expected xl for width=${w}`);
  }
  for (const invalid of [-1, Number.NaN, null, undefined, 'wide']) {
    assert.equal(
      resolveViewportTier(invalid),
      'mobile',
      `Expected mobile fallback for invalid width=${String(invalid)}`
    );
  }
});

// --- 2. index.html RTL, viewport, and Arabic typography setup ---

test('index.html enforces lang="ar", dir="rtl", iOS viewport-fit=cover, theme-color, and Tajawal Arabic font', () => {
  const indexHtmlPath = path.resolve(process.cwd(), 'index.html');
  const html = fs.readFileSync(indexHtmlPath, 'utf-8');

  assert.match(html, /<html[^>]+lang="ar"[^>]+dir="rtl"|<html[^>]+dir="rtl"[^>]+lang="ar"/);
  assert.match(
    html,
    /<meta[^>]+name="viewport"[^>]+content="width=device-width,\s*initial-scale=1\.0,\s*viewport-fit=cover"/
  );
  assert.match(html, /<meta[^>]+name="theme-color"[^>]+content="#0f766e"/);
  assert.match(
    html,
    /<link[^>]+rel="preconnect"[^>]+href="https:\/\/fonts\.googleapis\.com"/
  );
  assert.match(
    html,
    /<link[^>]+rel="preconnect"[^>]+href="https:\/\/fonts\.gstatic\.com"[^>]+crossorigin/
  );
  assert.match(
    html,
    /<link[^>]+rel="stylesheet"[^>]+href="https:\/\/fonts\.googleapis\.com\/css2\?family=Tajawal[^"]*display=swap"/
  );
});

// --- 3. React SSR RTL, semantic nav, bidi isolation, and popover alignment ---

test('App enforces root dir="rtl" lang="ar", semantic nav landmark, and runtime enforceDocumentRtl hook', () => {
  const appHtml = renderToStaticMarkup(<App />);
  assert.match(
    appHtml,
    /<main[^>]+dir="rtl"[^>]+lang="ar"|<main[^>]+lang="ar"[^>]+dir="rtl"/
  );
  assert.match(appHtml, /<nav[^>]+class="site-nav"[^>]+aria-label="التنقل الرئيسي"/);

  const appSrc = fs.readFileSync(path.resolve(process.cwd(), 'src/App.jsx'), 'utf-8');
  const mainSrc = fs.readFileSync(path.resolve(process.cwd(), 'src/main.jsx'), 'utf-8');
  assert.match(appSrc, /enforceDocumentRtl/);
  assert.match(mainSrc, /enforceDocumentRtl/);
});

test('Components enforce dir="rtl" containers, <bdi dir="ltr"> for embedded LTR labels/contacts, and end-aligned share menus', () => {
  const engagementHtml = renderToStaticMarkup(<EngagementSection forms={[sampleForm]} />);
  assert.match(engagementHtml, /<article[^>]+dir="rtl"[^>]+class="engagement-card/);
  assert.match(engagementHtml, /<bdi dir="ltr">Google Forms<\/bdi>/);

  const committeePanelHtml = renderToStaticMarkup(
    <CommitteeAdminPanel
      members={[
        {
          id: 1,
          fullName: 'فادي وليد اغبارية',
          role: 'رئيس اللجنة',
          email: 'Egb.fadi@gmail.com',
          phone: '050-1234567',
        },
      ]}
    />
  );
  assert.match(committeePanelHtml, /<bdi dir="ltr">Egb\.fadi@gmail\.com<\/bdi>/);
  assert.match(committeePanelHtml, /<bdi dir="ltr">050-1234567<\/bdi>/);

  const captionedMediaHtml = renderToStaticMarkup(
    <LazyMediaImage
      src="https://example.com/photo.webp"
      alt="صورة"
      caption="وصف الصورة"
    />
  );
  assert.match(captionedMediaHtml, /<figure[^>]+dir="rtl"/);

  const endMenuHtml = renderToStaticMarkup(
    <ShareActions
      item={samplePost}
      entityType="post"
      baseUrl="https://mahjar.example.org"
      menuAlign="end"
      initialMenuOpen={true}
    />
  );
  assert.match(endMenuHtml, /share-actions__menu--align-end/);

  const cardHtml = renderToStaticMarkup(
    <AnnouncementCard post={samplePost} shareBaseUrl="https://mahjar.example.org" />
  );
  assert.match(cardHtml, /aria-haspopup="menu"/);

  const cardSrc = fs.readFileSync(
    path.resolve(process.cwd(), 'src/components/AnnouncementCard.jsx'),
    'utf-8'
  );
  const detailSrc = fs.readFileSync(
    path.resolve(process.cwd(), 'src/components/PostDetailView.jsx'),
    'utf-8'
  );
  assert.match(cardSrc, /menuAlign="end"/);
  assert.match(detailSrc, /menuAlign="end"/);

  const detailHtml = renderToStaticMarkup(
    <PostDetailView
      post={samplePost}
      shareBaseUrl="https://mahjar.example.org"
      onClose={() => {}}
    />
  );
  assert.match(detailHtml, /aria-haspopup="menu"/);
});

// --- 4. styles.css mobile-first RTL, iOS/Android safeguards, and progressive breakpoints ---

test('styles.css enforces RTL typography, iOS/Android safeguards, ascending mobile-first breakpoints, and overflow protection', () => {
  const cssPath = path.resolve(process.cwd(), 'src/styles.css');
  const css = fs.readFileSync(cssPath, 'utf-8');

  // Root RTL + Arabic fonts + mobile browser safeguards
  assert.match(css, /direction:\s*rtl/);
  assert.match(css, /'Tajawal',\s*'Cairo',\s*'Noto Sans Arabic'/);
  assert.match(css, /-webkit-text-size-adjust:\s*100%/);
  assert.match(css, /overflow-x:\s*clip/);
  assert.match(css, /touch-action:\s*manipulation/);

  // 16px (1rem) inputs to prevent iOS Safari zoom on focus
  assert.match(
    css,
    /\.admin-input,\s*\.admin-select,\s*\.admin-textarea\s*\{[^}]*font-size:\s*1rem/s
  );

  // Mobile-first header stacks vertically on mobile and switches to row at >= 640px
  assert.match(
    css,
    /\.app-header__brand\s*\{[^}]*flex-direction:\s*column-reverse/s
  );
  assert.match(
    css,
    /@media\s*\(min-width:\s*640px\)[\s\S]*?\.app-header__brand\s*\{[^}]*flex-direction:\s*row/s
  );

  // Ascending mobile-first breakpoints (640, 768, 1024, 1280) with zero desktop-first max-width queries
  assert.doesNotMatch(css, /@media\s*\([^)]*max-width:/);
  const idx640 = css.indexOf('min-width: 640px');
  const idx768 = css.indexOf('min-width: 768px');
  const idx1024 = css.indexOf('min-width: 1024px');
  const idx1280 = css.indexOf('min-width: 1280px');
  assert.ok(
    idx640 !== -1 && idx768 !== -1 && idx1024 !== -1 && idx1280 !== -1,
    'styles.css must define progressive breakpoints at 640px, 768px, 1024px, and 1280px'
  );
  assert.ok(
    idx640 < idx768 && idx768 < idx1024 && idx1024 < idx1280,
    'Breakpoints should follow mobile-first ascending progression'
  );

  // Safe area insets & reduced motion
  assert.match(css, /env\(safe-area-inset-/);
  assert.match(css, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);

  // Popover containment & end alignment
  assert.match(
    css,
    /\.share-actions__menu\s*\{[^}]*max-width:\s*calc\(100vw\s*-\s*2rem\)/s
  );
  assert.match(
    css,
    /\.share-actions__menu--align-end\s*\{[^}]*inset-inline-end:\s*0/s
  );

  // Mobile compact select width -> desktop min-width
  assert.match(
    css,
    /\.admin-select--compact\s*\{[^}]*width:\s*100%/s
  );
  assert.match(
    css,
    /@media\s*\(min-width:\s*640px\)[\s\S]*?\.admin-select--compact\s*\{[^}]*min-width:\s*220px/s
  );

  // Grid item blowout prevention
  for (const selector of [
    '\\.announcements-feed__item',
    '\\.committee-directory__item',
    '\\.engagement-card',
    '\\.admin-field',
  ]) {
    assert.match(
      css,
      new RegExp(`${selector}[^{]*\\{[^}]*min-width:\\s*0`, 's'),
      `Selector ${selector} must include min-width: 0 to prevent grid track blowout`
    );
  }
});
