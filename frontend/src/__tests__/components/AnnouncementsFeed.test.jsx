import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import AnnouncementCard from '../../components/AnnouncementCard.jsx';
import AnnouncementsFeed, {
  POST_CATEGORIES,
  sortAndFilterPosts,
} from '../../components/AnnouncementsFeed.jsx';
import App from '../../App.jsx';

const samplePostsUnordered = [
  {
    id: 101,
    title: 'تعميم بخصوص مواعيد الدوام الشتوي',
    summary: 'نود إعلام الأهالي الكرام ببدء تطبيق التوقيت الشتوي في المدرسة اعتباراً من الأسبوع القادم.',
    category: 'general',
    publishedAt: '2026-11-10T08:00:00Z',
  },
  {
    id: 102,
    title: 'يوم التراث والهوية في مدرسة المحجر',
    summary: 'دعوة لأهالي الطلاب للمشاركة في فعاليات يوم التراث السنوي في ساحة المدرسة.',
    category: 'upcoming_event',
    publishedAt: '2026-11-24T10:30:00Z',
    eventDate: '2026-12-05',
    imageUrl: 'https://example.com/posts/heritage-day.webp',
  },
  {
    id: 103,
    title: 'مبادرة أصدقاء المكتبة والقراءة الحرة',
    summary: 'انطلاق نشاط القراءة الأسبوعي لطلاب الصفوف الأولى بإشراف معلمي اللغة العربية.',
    category: 'student_activity',
    publishedAt: '2026-11-18T12:15:00Z',
  },
  {
    id: 104,
    title: 'مستجدات مشروع تظليل ساحة المدرسة (العريشة)',
    summary: 'استكمال المرحلة الأولى من تركيب العريشة وتنظيم مسارات خروج الطلاب بأمان.',
    category: 'updates',
    publishedAt: '2026-11-22T16:45:00Z',
  },
];

test('POST_CATEGORIES defines all required filter categories with Arabic labels', () => {
  const categoryKeys = POST_CATEGORIES.map((c) => c.id);
  assert.deepEqual(
    categoryKeys,
    ['all', 'general', 'upcoming_event', 'student_activity', 'updates'],
    'POST_CATEGORIES must expose all and the 4 required category keys'
  );
});

test('sortAndFilterPosts orders posts in reverse-chronological order (newest first)', () => {
  const sorted = sortAndFilterPosts(samplePostsUnordered, 'all');
  const orderedIds = sorted.map((post) => post.id);

  assert.deepEqual(
    orderedIds,
    [102, 104, 103, 101],
    'Posts must be ordered from newest publishedAt timestamp to oldest'
  );
});

test('sortAndFilterPosts filters accurately by each category (general, upcoming_event, student_activity, updates)', () => {
  const generalPosts = sortAndFilterPosts(samplePostsUnordered, 'general');
  assert.equal(generalPosts.length, 1);
  assert.equal(generalPosts[0].id, 101);

  const eventPosts = sortAndFilterPosts(samplePostsUnordered, 'upcoming_event');
  assert.equal(eventPosts.length, 1);
  assert.equal(eventPosts[0].id, 102);

  const activityPosts = sortAndFilterPosts(samplePostsUnordered, 'student_activity');
  assert.equal(activityPosts.length, 1);
  assert.equal(activityPosts[0].id, 103);

  const updatePosts = sortAndFilterPosts(samplePostsUnordered, 'updates');
  assert.equal(updatePosts.length, 1);
  assert.equal(updatePosts[0].id, 104);
});

test('AnnouncementCard renders RTL card with title, summary, category badge, date, and optional lazy-loaded image', () => {
  const html = renderToStaticMarkup(
    <AnnouncementCard post={samplePostsUnordered[1]} />
  );

  assert.match(html, /dir="rtl"/, 'AnnouncementCard should enforce RTL direction');
  assert.ok(html.includes('يوم التراث والهوية في مدرسة المحجر'), 'Should display post title');
  assert.ok(
    html.includes('دعوة لأهالي الطلاب للمشاركة في فعاليات يوم التراث السنوي في ساحة المدرسة.'),
    'Should display post summary/content'
  );
  assert.ok(html.includes('فعالية قادمة'), 'Should display Arabic label for upcoming_event category');
  assert.match(
    html,
    /<img[^>]+src="https:\/\/example\.com\/posts\/heritage-day\.webp"/,
    'Should render post image when imageUrl is present'
  );
  assert.match(
    html,
    /<img[^>]+loading="lazy"/,
    'Post image must include loading="lazy" per NFR performance requirements'
  );
});

test('AnnouncementCard supports snake_case fields from Flask API payloads and omits image when not provided', () => {
  const snakeCasePost = {
    id: 205,
    title: 'لقاء مفتوح مع أولياء الأمور',
    content: 'يسر اللجنة دعوتكم لحضور اللقاء التشاوري الفصلي.',
    category: 'general',
    published_at: '2026-11-25T09:00:00Z',
    image_url: '   ',
  };

  const html = renderToStaticMarkup(<AnnouncementCard post={snakeCasePost} />);

  assert.ok(html.includes('لقاء مفتوح مع أولياء الأمور'), 'Should render title');
  assert.ok(html.includes('يسر اللجنة دعوتكم لحضور اللقاء التشاوري الفصلي.'), 'Should support content fallback');
  assert.ok(html.includes('إعلان عام'), 'Should render Arabic category badge for general');
  assert.doesNotMatch(html, /<img/, 'Should not render an <img> tag when image_url is empty/whitespace');
});

test('AnnouncementsFeed renders posts in reverse-chronological order in the DOM without category filter buttons', () => {
  const html = renderToStaticMarkup(
    <AnnouncementsFeed posts={samplePostsUnordered} />
  );

  assert.match(html, /dir="rtl"/, 'AnnouncementsFeed section must be RTL');
  assert.ok(html.includes('لوحة الإعلانات والفعاليات'), 'Should render Arabic section heading');

  // Verify category filter buttons/toolbar are completely removed
  assert.doesNotMatch(
    html,
    /role="toolbar"/,
    'AnnouncementsFeed must NOT render a category filter toolbar'
  );
  assert.doesNotMatch(
    html,
    /announcements-feed__filter-btn/,
    'AnnouncementsFeed must NOT render category filter buttons'
  );
  assert.doesNotMatch(
    html,
    /data-category=/,
    'AnnouncementsFeed must NOT render data-category filter buttons'
  );
  assert.ok(
    !html.includes('>الكل<'),
    'AnnouncementsFeed must NOT render "الكل" filter button'
  );

  // Verify post cards still display their category badges
  assert.ok(html.includes('إعلان عام'), 'Post card should display "إعلان عام" badge');
  assert.ok(html.includes('فعالية قادمة'), 'Post card should display "فعالية قادمة" badge');
  assert.ok(html.includes('نشاط طلابي'), 'Post card should display "نشاط طلابي" badge');
  assert.ok(html.includes('مستجدات'), 'Post card should display "مستجدات" badge');

  // Verify reverse-chronological order in rendered HTML
  const idxNewest = html.indexOf('يوم التراث والهوية في مدرسة المحجر'); // Nov 24
  const idxSecond = html.indexOf('مستجدات مشروع تظليل ساحة المدرسة (العريشة)'); // Nov 22
  const idxThird = html.indexOf('مبادرة أصدقاء المكتبة والقراءة الحرة'); // Nov 18
  const idxOldest = html.indexOf('تعميم بخصوص مواعيد الدوام الشتوي'); // Nov 10

  assert.ok(idxNewest !== -1 && idxSecond !== -1 && idxThird !== -1 && idxOldest !== -1, 'All posts should be rendered');
  assert.ok(
    idxNewest < idxSecond && idxSecond < idxThird && idxThird < idxOldest,
    'Posts must appear in reverse-chronological order (newest first) in the DOM'
  );
});

test('AnnouncementsFeed displays an Arabic empty state when there are no posts', () => {
  const html = renderToStaticMarkup(<AnnouncementsFeed posts={[]} />);

  assert.match(html, /dir="rtl"/, 'Empty state must remain RTL');
  assert.match(html, /role="status"/, 'Empty state should expose role="status"');
  assert.ok(
    html.includes('لا توجد إعلانات أو فعاليات'),
    'Should display Arabic empty state message when posts list is empty'
  );
});

test('App renders both the AnnouncementsFeed and CommitteeDirectory in a responsive RTL layout', () => {
  const html = renderToStaticMarkup(<App />);

  assert.match(html, /dir="rtl"/, 'App root must enforce RTL');
  assert.ok(html.includes('لوحة الإعلانات والفعاليات'), 'App should render AnnouncementsFeed section');
  assert.ok(html.includes('أعضاء لجنة أولياء الأمور'), 'App should render CommitteeDirectory section');
});

test('styles.css defines centered single-column Facebook-style vertical feed and uncropped natural image sizing', () => {
  const cssPath = path.resolve(process.cwd(), 'src/styles.css');
  const cssContent = fs.readFileSync(cssPath, 'utf-8');

  assert.match(
    cssContent,
    /\.announcements-feed__grid\s*\{[^}]*grid-template-columns:\s*1fr[^}]*max-width:\s*680px[^}]*margin:\s*0 auto/s,
    'Announcements feed must be a centered single-column vertical feed'
  );
  assert.doesNotMatch(
    cssContent,
    /@media\s*\(min-width:\s*(?:640|1024)px\)[\s\S]*?\.announcements-feed__grid\s*\{[^}]*repeat\(2/s,
    'Desktop breakpoints must keep single-column centered feed layout'
  );
  assert.match(
    cssContent,
    /\.announcement-card__image\s*\{[^}]*height:\s*auto[^}]*object-fit:\s*contain/s,
    'Feed images must preserve natural aspect ratio without cropping'
  );
});

test('AnnouncementsFeed displays all posts stacked one above another with full details inline and no show/hide details buttons', () => {
  const postsWithDetails = samplePostsUnordered.map((p, idx) =>
    idx === 1
      ? { ...p, content: 'تفاصيل كاملة ليوم التراث مع البرنامج الزمني.' }
      : p
  );
  const html = renderToStaticMarkup(<AnnouncementsFeed posts={postsWithDetails} />);

  assert.ok(html.includes('يوم التراث والهوية في مدرسة المحجر'));
  assert.ok(html.includes('تفاصيل كاملة ليوم التراث مع البرنامج الزمني.'));
  assert.ok(html.includes('مستجدات مشروع تظليل ساحة المدرسة (العريشة)'));
  assert.ok(html.includes('مبادرة أصدقاء المكتبة والقراءة الحرة'));
  assert.ok(html.includes('تعميم بخصوص مواعيد الدوام الشتوي'));
  assert.ok(!html.includes('عرض التفاصيل'), 'Show details button must be removed');
  assert.ok(!html.includes('إخفاء التفاصيل'), 'Hide details button must be removed');
});

test('sortAndFilterPosts honors explicit displayOrder ascending while preserving date order when omitted', () => {
  const customOrdered = [
    { ...samplePostsUnordered[0], displayOrder: 1 },
    { ...samplePostsUnordered[1], displayOrder: 2 },
    { ...samplePostsUnordered[2], displayOrder: 3 },
  ];
  assert.deepEqual(
    sortAndFilterPosts(customOrdered, 'all').map((p) => p.id),
    [101, 102, 103]
  );
});

test('AnnouncementCard omits show-more toggle for short posts and renders "عرض المزيد..." / "عرض أقل" for long or multi-line posts without duplicating text', () => {
  const shortHtml = renderToStaticMarkup(
    <AnnouncementCard post={samplePostsUnordered[0]} />
  );
  assert.ok(!shortHtml.includes('عرض المزيد...'), 'Short post must not render show-more button');
  assert.ok(!shortHtml.includes('عرض أقل'), 'Short post must not render show-less button');

  const fullLongText =
    'استمراراً لجهود اللجنة في توفير بيئة مدرسية آمنة ومريحة لأبنائنا، تم بحمد الله إنجاز المرحلة الأولى من مشروع العريشة. وتتقدم اللجنة بجزيل الشكر للأخ محمد شاكر إغبارية على مبادرته الكريمة. كما ندعوكم للمساهمة في دعم واستكمال هذا العمل المبارك، وذلك عبر التواصل مع أعضاء اللجنة أو المساهمة المباشرة في تكاليف التظليل الإضافية وتجهيز المقاعد للطلاب.';
  const truncatedFromApi = fullLongText.slice(0, 220).trimEnd() + '…';

  const apiPostWithContent = {
    id: 501,
    title: 'مستجدات مشروع تظليل ساحة المدرسة',
    summary: truncatedFromApi,
    content: fullLongText,
    category: 'updates',
    publishedAt: '2026-11-22T16:45:00Z',
    imageUrl: 'https://example.com/shade.webp',
  };

  const collapsedApiHtml = renderToStaticMarkup(
    <AnnouncementCard post={apiPostWithContent} />
  );
  assert.ok(
    collapsedApiHtml.includes('عرض المزيد...'),
    'Long post must render "عرض المزيد..." toggle button'
  );
  assert.match(
    collapsedApiHtml,
    /aria-expanded="false"/,
    'Collapsed toggle button must expose aria-expanded="false"'
  );
  assert.ok(
    !collapsedApiHtml.includes('تجهيز المقاعد للطلاب.'),
    'Collapsed card must hide overflow text until expanded'
  );
  assert.doesNotMatch(
    collapsedApiHtml,
    /announcement-card__details/,
    'Full content matching truncated summary must not be duplicated below the image'
  );

  const expandedApiHtml = renderToStaticMarkup(
    <AnnouncementCard post={apiPostWithContent} initialExpanded />
  );
  assert.ok(
    expandedApiHtml.includes('تجهيز المقاعد للطلاب.'),
    'Expanded card must display the full announcement text'
  );
  assert.ok(
    expandedApiHtml.includes('عرض أقل'),
    'Expanded card must switch toggle label to "عرض أقل"'
  );
  assert.match(
    expandedApiHtml,
    /aria-expanded="true"/,
    'Expanded toggle button must expose aria-expanded="true"'
  );
  assert.doesNotMatch(
    expandedApiHtml,
    /announcement-card__details/,
    'Expanded card must not duplicate full content below the image'
  );

  const longSummaryOnlyPost = {
    id: 502,
    title: 'إعلان طويل بدون حقل content',
    summary: fullLongText,
    category: 'general',
    publishedAt: '2026-11-21T10:00:00Z',
  };
  const longSummaryCollapsedHtml = renderToStaticMarkup(
    <AnnouncementCard post={longSummaryOnlyPost} />
  );
  assert.ok(longSummaryCollapsedHtml.includes('عرض المزيد...'));
  assert.ok(!longSummaryCollapsedHtml.includes('تجهيز المقاعد للطلاب.'));

  const multilinePost = {
    id: 503,
    title: 'إعلان متعدد الأسطر',
    summary: 'السطر الأول\nالسطر الثاني\nالسطر الثالث\nالسطر الرابع\nالسطر الخامس المخفي',
    category: 'general',
    publishedAt: '2026-11-20T10:00:00Z',
  };
  const multilineCollapsedHtml = renderToStaticMarkup(
    <AnnouncementCard post={multilinePost} />
  );
  assert.ok(multilineCollapsedHtml.includes('عرض المزيد...'));
  assert.ok(!multilineCollapsedHtml.includes('السطر الخامس المخفي'));

  const multilineExpandedHtml = renderToStaticMarkup(
    <AnnouncementCard post={multilinePost} initialExpanded />
  );
  assert.ok(multilineExpandedHtml.includes('السطر الخامس المخفي'));
  assert.ok(multilineExpandedHtml.includes('عرض أقل'));
});

test('styles.css defines accessible >= 44x44px toggle button and pre-line wrapping for announcement text', () => {
  const cssPath = path.resolve(process.cwd(), 'src/styles.css');
  const cssContent = fs.readFileSync(cssPath, 'utf-8');

  assert.match(
    cssContent,
    /\.announcement-card__summary\s*\{[^}]*white-space:\s*pre-line/s,
    '.announcement-card__summary must preserve line breaks with white-space: pre-line'
  );
  assert.match(
    cssContent,
    /\.announcement-card__toggle-btn\s*\{[^}]*min-height:\s*44px[^}]*min-width:\s*44px/s,
    '.announcement-card__toggle-btn must define >= 44x44px accessible touch target'
  );
});
