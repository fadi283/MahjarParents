import React from 'react';
import AnnouncementCard, { CATEGORY_LABELS } from './AnnouncementCard.jsx';

export const POST_CATEGORIES = [
  { id: 'all', label: 'الكل' },
  { id: 'general', label: CATEGORY_LABELS.general },
  { id: 'upcoming_event', label: CATEGORY_LABELS.upcoming_event },
  { id: 'student_activity', label: CATEGORY_LABELS.student_activity },
  { id: 'updates', label: CATEGORY_LABELS.updates },
];

function parsePostDisplayOrder(post) {
  const raw = post?.displayOrder ?? post?.display_order;
  if (raw === null || raw === undefined || raw === '' || typeof raw === 'boolean') {
    return null;
  }
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : null;
}

export function sortAndFilterPosts(posts = [], selectedCategory = 'all') {
  if (!Array.isArray(posts)) return [];

  const normalizedCategory = (selectedCategory || 'all').trim();

  const filtered =
    normalizedCategory === 'all'
      ? [...posts]
      : posts.filter((post) => (post?.category ?? 'general') === normalizedCategory);

  return filtered.sort((a, b) => {
    const orderA = parsePostDisplayOrder(a);
    const orderB = parsePostDisplayOrder(b);
    if (orderA !== null || orderB !== null) {
      if (orderA === null) return 1;
      if (orderB === null) return -1;
      if (orderA !== orderB) {
        return orderA - orderB;
      }
    }

    const rawDateA =
      a?.publishedAt ?? a?.published_at ?? a?.createdAt ?? a?.created_at ?? '';
    const rawDateB =
      b?.publishedAt ?? b?.published_at ?? b?.createdAt ?? b?.created_at ?? '';

    const timeA = rawDateA ? new Date(rawDateA).getTime() : 0;
    const timeB = rawDateB ? new Date(rawDateB).getTime() : 0;

    const validTimeA = Number.isNaN(timeA) ? 0 : timeA;
    const validTimeB = Number.isNaN(timeB) ? 0 : timeB;

    if (validTimeB !== validTimeA) {
      return validTimeB - validTimeA;
    }

    return (Number(b?.id) || 0) - (Number(a?.id) || 0);
  });
}

export default function AnnouncementsFeed({
  posts = [],
  shareBaseUrl,
}) {
  const visiblePosts = sortAndFilterPosts(posts, 'all');

  return (
    <section
      id="announcements-feed"
      dir="rtl"
      className="announcements-feed"
      aria-labelledby="announcements-feed-heading"
    >
      <div className="announcements-feed__header">
        <div className="announcements-feed__title-group">
          <h2
            id="announcements-feed-heading"
            className="announcements-feed__title"
          >
            لوحة الإعلانات والفعاليات
          </h2>
          <p className="announcements-feed__subtitle">
            تابع أحدث الإعلانات المدرسية، الفعاليات القادمة، والأنشطة الطلابية والمستجدات مرتبة من الأحدث إلى الأقدم.
          </p>
        </div>
      </div>

      {visiblePosts.length === 0 ? (
        <div className="announcements-feed__empty" role="status">
          <p>لا توجد إعلانات أو فعاليات منشورة حالياً.</p>
        </div>
      ) : (
        <div className="announcements-feed__grid" role="feed" aria-busy="false">
          {visiblePosts.map((post, index) => (
            <div
              key={post.id ?? `${post.title}-${index}`}
              className="announcements-feed__item"
            >
              <AnnouncementCard
                post={post}
                shareBaseUrl={shareBaseUrl}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
