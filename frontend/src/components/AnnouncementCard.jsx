import React from 'react';
import {
  ALLOWED_EXTERNAL_MEDIA_TYPES,
  MEDIA_TYPE_LABELS,
  extractPostMedia,
  sanitizeImageUrl,
} from '../utils/mediaEmbeds.js';
import LazyMediaImage from './LazyMediaImage.jsx';
import PostMediaGallery from './PostMediaGallery.jsx';
import ShareActions from './ShareActions.jsx';

export const CATEGORY_LABELS = {
  general: 'إعلان عام',
  upcoming_event: 'فعالية قادمة',
  student_activity: 'نشاط طلابي',
  updates: 'مستجدات',
};

export function formatArabicDate(isoDateString) {
  if (!isoDateString) return '';
  const parsed = new Date(isoDateString);
  if (Number.isNaN(parsed.getTime())) {
    return String(isoDateString);
  }
  try {
    return new Intl.DateTimeFormat('ar-EG', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    }).format(parsed);
  } catch {
    return isoDateString.slice(0, 10);
  }
}

export default function AnnouncementCard({
  post,
  shareBaseUrl,
}) {
  if (!post) return null;

  const title = (post.title ?? '').trim();
  const summary = (
    post.summary ??
    post.content ??
    post.description ??
    ''
  ).trim();
  const fullBody = (post.content ?? post.body ?? post.details ?? '').trim();
  const extraBody = fullBody && fullBody !== summary ? fullBody : '';
  const category = (post.category ?? 'general').trim();
  const categoryLabel = CATEGORY_LABELS[category] ?? CATEGORY_LABELS.general;
  const publishedAt =
    post.publishedAt ?? post.published_at ?? post.createdAt ?? post.created_at ?? '';
  const eventDate = post.eventDate ?? post.event_date ?? '';
  const rawImageUrl = post.imageUrl ?? post.image_url ?? '';
  const safeImageUrl = sanitizeImageUrl(rawImageUrl);

  const { embeds } = extractPostMedia(post);
  const presentMediaTypes = ALLOWED_EXTERNAL_MEDIA_TYPES.filter((type) =>
    embeds.some((embed) => embed.mediaType === type)
  );

  const formattedPublishedDate = formatArabicDate(publishedAt);
  const formattedEventDate = formatArabicDate(eventDate);

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
      className={`announcement-card announcement-card--${category}`}
      aria-label={`${title} - ${categoryLabel}`}
    >
      <div className="announcement-card__body">
        <div className="announcement-card__meta">
          <span
            className={`announcement-card__badge announcement-card__badge--${category}`}
          >
            {categoryLabel}
          </span>

          {formattedPublishedDate && (
            <time
              className="announcement-card__date"
              dateTime={publishedAt}
            >
              {formattedPublishedDate}
            </time>
          )}
        </div>

        <h3 className="announcement-card__title">{title}</h3>

        <p className="announcement-card__summary">{summary}</p>

        {formattedEventDate && (
          <div className="announcement-card__event-date">
            <span className="announcement-card__event-label">موعد الفعالية:</span>{' '}
            <time dateTime={eventDate}>{formattedEventDate}</time>
          </div>
        )}

        {safeImageUrl && (
          <div className="announcement-card__media">
            <LazyMediaImage
              src={safeImageUrl}
              alt={title}
              className="announcement-card__image"
            />
          </div>
        )}

        {(extraBody || embeds.length > 0 || (post.images ?? post.gallery)?.length > 0) && (
          <div className="announcement-card__details">
            {extraBody && <p className="post-detail__content">{extraBody}</p>}
            <PostMediaGallery
              post={post}
              excludeImageUrls={safeImageUrl ? [safeImageUrl] : []}
            />
          </div>
        )}

        <div className="announcement-card__footer">
          {presentMediaTypes.length > 0 && (
            <div className="announcement-card__media-badges">
              {presentMediaTypes.map((type) => (
                <span
                  key={type}
                  className={`announcement-card__media-pill announcement-card__media-pill--${type}`}
                >
                  {MEDIA_TYPE_LABELS[type]}
                </span>
              ))}
            </div>
          )}

          <div className="announcement-card__actions">
            <ShareActions
              item={post}
              entityType="post"
              baseUrl={shareBaseUrl}
              menuAlign="end"
            />
          </div>
        </div>
      </div>
    </article>
  );
}
