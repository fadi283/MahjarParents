import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import AnnouncementCard from '../components/AnnouncementCard.jsx';
import AnnouncementsFeed, {
  POST_CATEGORIES,
  sortAndFilterPosts,
} from '../components/AnnouncementsFeed.jsx';
import App from '../App.jsx';

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

test('AnnouncementsFeed renders posts in reverse-chronological order in the DOM with accessible category filter controls', () => {
  const html = renderToStaticMarkup(
    <AnnouncementsFeed posts={samplePostsUnordered} />
  );

  assert.match(html, /dir="rtl"/, 'AnnouncementsFeed section must be RTL');
  assert.ok(html.includes('لوحة الإعلانات والفعاليات'), 'Should render Arabic section heading');

  // Verify all category filter buttons exist with >= 44x44px touch targets
  assert.ok(html.includes('الكل'), 'Should render "الكل" filter button');
  assert.ok(html.includes('إعلان عام'), 'Should render "إعلان عام" filter button');
  assert.ok(html.includes('فعالية قادمة'), 'Should render "فعالية قادمة" filter button');
  assert.ok(html.includes('نشاط طلابي'), 'Should render "نشاط طلابي" filter button');
  assert.ok(html.includes('مستجدات'), 'Should render "مستجدات" filter button');
  assert.match(html, /min-height:\s*44px/, 'Category filter buttons must enforce min-height: 44px');
  assert.match(html, /min-width:\s*44px/, 'Category filter buttons must enforce min-width: 44px');

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

test('AnnouncementsFeed filters rendered posts when initialCategory / activeCategory is specified', () => {
  const html = renderToStaticMarkup(
    <AnnouncementsFeed
      posts={samplePostsUnordered}
      initialCategory="student_activity"
    />
  );

  assert.ok(
    html.includes('مبادرة أصدقاء المكتبة والقراءة الحرة'),
    'Should render matching student_activity post'
  );
  assert.ok(
    !html.includes('تعميم بخصوص مواعيد الدوام الشتوي'),
    'Should not render general post when filtered by student_activity'
  );
  assert.ok(
    !html.includes('يوم التراث والهوية في مدرسة المحجر'),
    'Should not render upcoming_event post when filtered by student_activity'
  );
  assert.match(
    html,
    /aria-pressed="true"[^>]*>[^<]*نشاط طلابي/,
    'Active category filter button should have aria-pressed="true"'
  );
});

test('AnnouncementsFeed displays an Arabic empty state when no posts match the selected category', () => {
  const onlyGeneralPosts = [samplePostsUnordered[0]];
  const html = renderToStaticMarkup(
    <AnnouncementsFeed
      posts={onlyGeneralPosts}
      initialCategory="upcoming_event"
    />
  );

  assert.match(html, /dir="rtl"/, 'Empty state must remain RTL');
  assert.ok(
    html.includes('لا توجد إعلانات أو فعاليات في هذا التصنيف حالياً'),
    'Should display Arabic empty state message when filtered list is empty'
  );
});

test('App renders both the AnnouncementsFeed and CommitteeDirectory in a responsive RTL layout', () => {
  const html = renderToStaticMarkup(<App />);

  assert.match(html, /dir="rtl"/, 'App root must enforce RTL');
  assert.ok(html.includes('لوحة الإعلانات والفعاليات'), 'App should render AnnouncementsFeed section');
  assert.ok(html.includes('أعضاء لجنة أولياء الأمور'), 'App should render CommitteeDirectory section');
});

test('styles.css defines mobile-first grid and desktop responsive breakpoints for announcements-feed', () => {
  const cssPath = path.resolve(process.cwd(), 'src/styles.css');
  const cssContent = fs.readFileSync(cssPath, 'utf-8');

  assert.match(
    cssContent,
    /\.announcements-feed__grid\s*\{[^}]*grid-template-columns:\s*1fr/,
    'Mobile-first default grid for announcements feed must be 1 column'
  );
  assert.match(
    cssContent,
    /@media\s*\(min-width:\s*640px\)[\s\S]*?\.announcements-feed__grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*1fr\)/,
    'Tablet/desktop breakpoint must expand announcements feed grid to multi-column layout'
  );
});
