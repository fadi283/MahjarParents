import React from 'react';
import { resolveExternalMediaEmbed } from '../utils/mediaEmbeds.js';

export default function ExternalMediaEmbed({
  media,
  title = '',
  className = '',
}) {
  const resolved = resolveExternalMediaEmbed(media);
  if (!resolved) return null;

  const isVideo = resolved.mediaType === 'video';
  const explicitTitle = typeof title === 'string' ? title.trim() : '';
  const frameTitle =
    explicitTitle ||
    resolved.title ||
    (isVideo
      ? `مشغل فيديو - ${resolved.providerLabel}`
      : `مشغل صوت - ${resolved.providerLabel}`);

  const badgeLabel = isVideo
    ? `فيديو • ${resolved.providerLabel}`
    : `تسجيل صوتي • ${resolved.providerLabel}`;

  const touchTargetStyle = {
    minHeight: '44px',
    minWidth: '44px',
  };

  const figureClassName = [
    'media-embed',
    `media-embed--${resolved.mediaType}`,
    `media-embed--${resolved.provider}`,
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const wrapperClassName = isVideo
    ? 'media-embed__frame-wrapper media-embed__frame-wrapper--video'
    : `media-embed__frame-wrapper media-embed__frame-wrapper--audio media-embed__frame-wrapper--${resolved.provider}`;

  return (
    <figure
      dir="rtl"
      className={figureClassName}
      data-provider={resolved.provider}
      data-media-type={resolved.mediaType}
    >
      <div className="media-embed__header">
        <span className="media-embed__badge">{badgeLabel}</span>
        <a
          href={resolved.canonicalUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="media-embed__external-link"
          style={touchTargetStyle}
        >
          فتح في نافذة جديدة
        </a>
      </div>

      <div className={wrapperClassName}>
        <iframe
          src={resolved.embedUrl}
          title={frameTitle}
          loading="lazy"
          referrerPolicy="strict-origin-when-cross-origin"
          sandbox="allow-scripts allow-same-origin allow-presentation allow-popups"
          allow={
            isVideo
              ? 'accelerometer; encrypted-media; gyroscope; picture-in-picture; fullscreen'
              : 'encrypted-media'
          }
          allowFullScreen={isVideo}
          className="media-embed__iframe"
        />
      </div>
    </figure>
  );
}
