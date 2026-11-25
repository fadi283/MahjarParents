import React, { useEffect, useState } from 'react';
import AnnouncementCard, { CATEGORY_LABELS } from './AnnouncementCard.jsx';
import PostDetailView from './PostDetailView.jsx';
import { parsePostIdFromLocation } from '../utils/whatsappShare.js';

export const POST_CATEGORIES = [
  { id: 'all', label: 'الكل' },
  { id: 'general', label: CATEGORY_LABELS.general },
  { id: 'upcoming_event', label: CATEGORY_LABELS.upcoming_event },
  { id: 'student_activity', label: CATEGORY_LABELS.student_activity },
  { id: 'updates', label: CATEGORY_LABELS.updates },
];

export function sortAndFilterPosts(posts = [], selectedCategory = 'all') {
  if (!Array.isArray(posts)) return [];

  const normalizedCategory = (selectedCategory || 'all').trim();

  const filtered =
    normalizedCategory === 'all'
      ? [...posts]
      : posts.filter((post) => (post?.category ?? 'general') === normalizedCategory);

  return filtered.sort((a, b) => {
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
  initialCategory = 'all',
  initialSelectedPostId = null,
  shareBaseUrl,
  onCategoryChange,
  onSelectPost,
}) {
  const [activeCategory, setActiveCategory] = useState(initialCategory);
  const [selectedPostId, setSelectedPostId] = useState(
    () =>
      initialSelectedPostId ??
      (typeof window !== 'undefined'
        ? parsePostIdFromLocation(window.location)
        : null)
  );

  useEffect(() => {
    if (typeof window === 'undefined' || initialSelectedPostId !== null) {
      return undefined;
    }

    const syncFromLocation = () => {
      setSelectedPostId(parsePostIdFromLocation(window.location));
    };

    window.addEventListener('hashchange', syncFromLocation);
    window.addEventListener('popstate', syncFromLocation);
    return () => {
      window.removeEventListener('hashchange', syncFromLocation);
      window.removeEventListener('popstate', syncFromLocation);
    };
  }, [initialSelectedPostId]);

  const handleSelectCategory = (categoryId) => {
    setActiveCategory(categoryId);
    setSelectedPostId(null);
    if (typeof onCategoryChange === 'function') {
      onCategoryChange(categoryId);
    }
  };

  const handleSelectPost = (post) => {
    if (!post) return;
    setSelectedPostId(post.id);
    if (
      typeof window !== 'undefined' &&
      initialSelectedPostId === null &&
      post.id !== null &&
      post.id !== undefined
    ) {
      const targetHash = `#post-${encodeURIComponent(String(post.id).trim())}`;
      if (window.location.hash !== targetHash) {
        window.history.pushState(null, '', targetHash);
      }
    }
    if (typeof onSelectPost === 'function') {
      onSelectPost(post);
    }
  };

  const handleClosePost = () => {
    setSelectedPostId(null);
    if (
      typeof window !== 'undefined' &&
      initialSelectedPostId === null &&
      parsePostIdFromLocation(window.location) !== null
    ) {
      window.history.replaceState(
        null,
        '',
        `${window.location.pathname || '/'}${window.location.search || ''}`
      );
    }
  };

  const selectedPost =
    selectedPostId !== null && selectedPostId !== undefined && Array.isArray(posts)
      ? posts.find((post) => String(post?.id) === String(selectedPostId)) ?? null
      : null;

  const visiblePosts = sortAndFilterPosts(posts, activeCategory);

  const touchTargetStyle = {
    minHeight: '44px',
    minWidth: '44px',
  };

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

        <div
          className="announcements-feed__filters"
          role="toolbar"
          aria-label="تصفية الإعلانات حسب التصنيف"
        >
          {POST_CATEGORIES.map((category) => {
            const isActive = activeCategory === category.id;
            return (
              <button
                key={category.id}
                type="button"
                className={`announcements-feed__filter-btn ${
                  isActive ? 'announcements-feed__filter-btn--active' : ''
                }`}
                style={touchTargetStyle}
                aria-pressed={isActive ? 'true' : 'false'}
                data-category={category.id}
                onClick={() => handleSelectCategory(category.id)}
              >
                {category.label}
              </button>
            );
          })}
        </div>
      </div>

      {selectedPost ? (
        <PostDetailView
          post={selectedPost}
          shareBaseUrl={shareBaseUrl}
          onClose={handleClosePost}
        />
      ) : visiblePosts.length === 0 ? (
        <div className="announcements-feed__empty" role="status">
          <p>لا توجد إعلانات أو فعاليات في هذا التصنيف حالياً.</p>
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
                onSelectPost={handleSelectPost}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
