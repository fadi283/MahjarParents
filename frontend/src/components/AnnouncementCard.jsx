import React, { useState } from 'react';
import {
  ALLOWED_EXTERNAL_MEDIA_TYPES,
  MEDIA_TYPE_LABELS,
  extractPostMedia,
  sanitizeImageUrl,
} from '../utils/mediaEmbeds.js';
import LazyMediaImage from './LazyMediaImage.jsx';
import PostMediaGallery from './PostMediaGallery.jsx';
import ShareActions from './ShareActions.jsx';

export const SUMMARY_PREVIEW_MAX_LENGTH = 280;
export const SUMMARY_PREVIEW_MAX_LINES = 4;

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

/**
 * Compute full text, collapsed preview text, truncation status, and separate details
 * for an announcement card without duplicating truncated summaries.
 */
export function buildAnnouncementTextState(post) {
  const rawSummary = String(post?.summary ?? post?.description ?? '')
    .replace(/\r\n?/g, '\n')
    .trim();
  const rawContent = String(post?.content ?? post?.body ?? post?.details ?? '')
    .replace(/\r\n?/g, '\n')
    .trim();

  let fullText = '';
  let separateDetails = '';

  if (!rawContent || rawContent === rawSummary) {
    fullText = rawSummary;
  } else if (!rawSummary) {
    fullText = rawContent;
  } else {
    const normalizedContent = rawContent.replace(/\s+/g, ' ').trim();
    const normalizedSummaryPrefix = rawSummary
      .replace(/(?:…|\.{3})$/, '')
      .replace(/\s+/g, ' ')
      .trim();

    if (
      normalizedSummaryPrefix.length > 0 &&
      normalizedContent.startsWith(normalizedSummaryPrefix)
    ) {
      fullText = rawContent;
    } else {
      fullText = rawSummary;
      separateDetails = rawContent;
    }
  }

  const lines = fullText ? fullText.split('\n') : [];
  const exceedsLines = lines.length > SUMMARY_PREVIEW_MAX_LINES;
  const exceedsLength = fullText.length > SUMMARY_PREVIEW_MAX_LENGTH;

  if (!exceedsLines && !exceedsLength) {
    return {
      fullText,
      previewText: fullText,
      isTruncated: false,
      separateDetails,
    };
  }

  let candidate = exceedsLines
    ? lines.slice(0, SUMMARY_PREVIEW_MAX_LINES).join('\n')
    : fullText;

  const maxSlice = SUMMARY_PREVIEW_MAX_LENGTH - 1;
  if (candidate.length > maxSlice) {
    const sliced = candidate.slice(0, maxSlice);
    const lastSpace = Math.max(sliced.lastIndexOf(' '), sliced.lastIndexOf('\n'));
    candidate =
      lastSpace >= Math.floor(maxSlice * 0.6) ? sliced.slice(0, lastSpace) : sliced;
  }

  candidate = candidate.trimEnd();
  const previewText = /(?:…|\.{3})$/.test(candidate) ? candidate : `${candidate}…`;

  return {
    fullText,
    previewText,
    isTruncated: true,
    separateDetails,
  };
}

export default function AnnouncementCard({
  post,
  shareBaseUrl,
  initialExpanded = false,
}) {
  const [isExpanded, setIsExpanded] = useState(Boolean(initialExpanded));

  if (!post) return null;

  const title = (post.title ?? '').trim();
  const { fullText, previewText, isTruncated, separateDetails } =
    buildAnnouncementTextState(post);
  const displayedText = isExpanded || !isTruncated ? fullText : previewText;
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

        <div className="announcement-card__summary-block">
          <p className="announcement-card__summary">{displayedText}</p>
          {isTruncated && (
            <button
              type="button"
              className="announcement-card__toggle-btn"
              aria-expanded={isExpanded}
              onClick={() => setIsExpanded((prev) => !prev)}
            >
              {isExpanded ? 'عرض أقل' : 'عرض المزيد...'}
            </button>
          )}
        </div>

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

        {(separateDetails || embeds.length > 0 || (post.images ?? post.gallery)?.length > 0) && (
          <div className="announcement-card__details">
            {separateDetails && <p className="post-detail__content">{separateDetails}</p>}
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
