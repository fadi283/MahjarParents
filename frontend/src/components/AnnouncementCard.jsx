import React from 'react';
import { extractPostMedia, sanitizeImageUrl } from '../utils/mediaEmbeds.js';
import LazyMediaImage from './LazyMediaImage.jsx';
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

export default function AnnouncementCard({ post, onSelectPost, shareBaseUrl }) {
  if (!post) return null;

  const title = (post.title ?? '').trim();
  const summary = (
    post.summary ??
    post.content ??
    post.description ??
    ''
  ).trim();
  const category = (post.category ?? 'general').trim();
  const categoryLabel = CATEGORY_LABELS[category] ?? CATEGORY_LABELS.general;
  const publishedAt =
    post.publishedAt ?? post.published_at ?? post.createdAt ?? post.created_at ?? '';
  const eventDate = post.eventDate ?? post.event_date ?? '';
  const rawImageUrl = post.imageUrl ?? post.image_url ?? '';
  const safeImageUrl = sanitizeImageUrl(rawImageUrl);

  const { embeds } = extractPostMedia(post);
  const hasVideoEmbed = embeds.some((embed) => embed.mediaType === 'video');
  const hasAudioEmbed = embeds.some((embed) => embed.mediaType === 'audio');
  const hasDetailAction = typeof onSelectPost === 'function';

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
      className={`announcement-card announcement-card--${category}`}
      aria-label={`${title} - ${categoryLabel}`}
    >
      {safeImageUrl && (
        <div className="announcement-card__media">
          <LazyMediaImage
            src={safeImageUrl}
            alt={title}
            className="announcement-card__image"
          />
        </div>
      )}

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

        <div className="announcement-card__footer">
          {(hasVideoEmbed || hasAudioEmbed) && (
            <div className="announcement-card__media-badges">
              {hasVideoEmbed && (
                <span className="announcement-card__media-pill announcement-card__media-pill--video">
                  فيديو
                </span>
              )}
              {hasAudioEmbed && (
                <span className="announcement-card__media-pill announcement-card__media-pill--audio">
                  صوت
                </span>
              )}
            </div>
          )}

          <div className="announcement-card__actions">
            <ShareActions item={post} entityType="post" baseUrl={shareBaseUrl} />

            {hasDetailAction && (
              <button
                type="button"
                className="announcement-card__detail-btn"
                style={touchTargetStyle}
                onClick={() => onSelectPost(post)}
              >
                عرض التفاصيل
              </button>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
