import React from 'react';
import { CATEGORY_LABELS, formatArabicDate } from './AnnouncementCard.jsx';
import PostMediaGallery from './PostMediaGallery.jsx';
import ShareActions from './ShareActions.jsx';

export default function PostDetailView({ post, onClose, shareBaseUrl }) {
  if (!post) return null;

  const title = (post.title ?? '').trim();
  const body =
    [post.content, post.body, post.details, post.summary, post.description]
      .find((value) => typeof value === 'string' && value.trim().length > 0)
      ?.trim() ?? '';
  const category = (post.category ?? 'general').trim();
  const categoryLabel = CATEGORY_LABELS[category] ?? CATEGORY_LABELS.general;
  const publishedAt =
    post.publishedAt ?? post.published_at ?? post.createdAt ?? post.created_at ?? '';
  const eventDate = post.eventDate ?? post.event_date ?? '';

  const formattedPublishedDate = formatArabicDate(publishedAt);
  const formattedEventDate = formatArabicDate(eventDate);

  const touchTargetStyle = {
    minHeight: '44px',
    minWidth: '44px',
  };

  const postDomId =
    post.id !== null &&
    post.id !== undefined &&
    String(post.id).trim() !== ''
      ? `post-${String(post.id).trim()}`
      : undefined;

  return (
    <article
      id={postDomId}
      dir="rtl"
      className={`post-detail post-detail--${category}`}
      aria-labelledby="post-detail-title"
    >
      <div className="post-detail__toolbar">
        {typeof onClose === 'function' && (
          <button
            type="button"
            className="post-detail__back-btn"
            style={touchTargetStyle}
            onClick={onClose}
          >
            العودة إلى قائمة الإعلانات
          </button>
        )}
        <ShareActions
          item={post}
          entityType="post"
          baseUrl={shareBaseUrl}
          menuAlign="end"
        />
      </div>

      <header className="post-detail__header">
        <div className="post-detail__meta">
          <span
            className={`announcement-card__badge announcement-card__badge--${category}`}
          >
            {categoryLabel}
          </span>

          {formattedPublishedDate && (
            <time
              className="post-detail__date"
              dateTime={publishedAt}
            >
              {formattedPublishedDate}
            </time>
          )}
        </div>

        <h3 id="post-detail-title" className="post-detail__title">
          {title}
        </h3>

        {formattedEventDate && (
          <div className="announcement-card__event-date">
            <span className="announcement-card__event-label">موعد الفعالية:</span>{' '}
            <time dateTime={eventDate}>{formattedEventDate}</time>
          </div>
        )}
      </header>

      {body && <p className="post-detail__content">{body}</p>}

      <PostMediaGallery post={post} />
    </article>
  );
}
